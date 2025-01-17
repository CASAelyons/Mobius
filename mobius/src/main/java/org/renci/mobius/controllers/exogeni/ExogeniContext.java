package org.renci.mobius.controllers.exogeni;

import com.google.common.collect.ArrayListMultimap;
import com.google.common.collect.Multimap;
import com.google.common.net.InetAddresses;
import org.json.simple.JSONArray;
import org.json.simple.JSONObject;
import org.renci.mobius.controllers.CloudContext;
import org.renci.mobius.controllers.MobiusException;
import org.renci.mobius.controllers.SliceNotFoundOrDeadException;
import org.renci.mobius.model.ComputeRequest;
import org.renci.mobius.model.StitchRequest;
import org.renci.mobius.model.StorageRequest;
import org.springframework.data.util.Pair;
import org.springframework.http.HttpStatus;
import org.apache.log4j.Logger;


import java.util.*;

/*
 * @brief class represents context for all resources on a specific region on exogeni. It maintains
 *        SliceContext per slice.
 *
 * @author kthare10
 */
public class ExogeniContext extends CloudContext {
    private static final Logger LOGGER = Logger.getLogger( ExogeniContext.class.getName() );
    private HashMap<String, SliceContext> sliceContextHashMap;
    private Multimap<Date, String> leaseEndTimeToSliceNameHashMap;


    /*
     * @brief constructor
     *
     * @param t - cloud type
     * @param s - site
     * @param workflowId - workflow id
     *
     *
     */
    public ExogeniContext(CloudContext.CloudType t, String s, String workflowId) {
        super(t, s, workflowId);
        sliceContextHashMap = new HashMap<>();
        leaseEndTimeToSliceNameHashMap = ArrayListMultimap.create();
    }

    /*
     * @brief function to generate JSONArray representing all the slice contexts held in this context
     *
     * @return JSONArray
     */
    @Override
    public JSONArray toJson() {
        synchronized (this) {
            JSONArray slices = null;
            if (sliceContextHashMap != null && sliceContextHashMap.size() != 0) {
                slices = new JSONArray();
                SliceContext context = null;
                for (HashMap.Entry<String, SliceContext> entry : sliceContextHashMap.entrySet()) {
                    context = entry.getValue();
                    JSONObject slice = new JSONObject();
                    slice.put("name", context.getSliceName());
                    if (context.getExpiry() != null) {
                        slice.put("expiry", Long.toString(context.getExpiry().getTime()));
                    }
                    slices.add(slice);
                }
            }
            return slices;
        }
    }

    /*
     * @brief build the context from JSONArray read from database; invoked when contexts are loaded
     *        on mobius restart
     *
     * @param array - json array representing all the slice contexts
     */
    @Override
    public void fromJson(JSONArray array) {
        synchronized (this) {
            if (array != null) {
                for (Object object : array) {
                    JSONObject slice = (JSONObject) object;
                    String sliceName = (String) slice.get("name");
                    LOGGER.debug("fromJson(): sliceName=" + sliceName);
                    SliceContext sliceContext = new SliceContext(sliceName);
                    String expiry = (String) slice.get("expiry");
                    LOGGER.debug("fromJson(): expiry=" + expiry);
                    if (expiry != null) {
                        sliceContext.setExpiry(expiry);
                    }
                    sliceContextHashMap.put(sliceName, sliceContext);
                }
            } else {
                LOGGER.error("fromJson(): Null array passed");
            }
        }
    }

    /*
     * @brief add cloud specific info to JSON Object representing ExogeniContext;
     *        JSON Object is saved to database
     *
     * @param object - json object representing ExogeniContext
     */
    @Override
    public JSONObject addCloudSpecificDataToJson(JSONObject object) {
        return object;
    }

    /*
     * @brief function to load cloud specific data from JSON Object representing ExogeniContext
     *
     * @param object - json object representing ExogeniContext
     */
    @Override
    public void loadCloudSpecificDataFromJson(JSONObject object) {
    }

    /*
     * @brief validate compute request; ignore leaseStart and leaseEnd time validation for future requests
     *
     * @param request - compute request
     * @param isFutureRequest - flag indicating if request is future request
     *
     * @throws Exception in case validation fails
     *
     */
    protected void validateComputeRequest(ComputeRequest request, boolean isFutureRequest) throws Exception {
        LOGGER.debug("validateComputeRequest: IN");

        if(request.getGpus() > 0) {
            throw new MobiusException(HttpStatus.BAD_REQUEST, "Exogeni does not support Gpus");
        }

        if(!request.isCoallocate() && request.getIpAddress() != null) {
            throw new MobiusException(HttpStatus.BAD_REQUEST, "IP address can only be specified with coallocate=true");
        }

        if(request.getIpAddress() != null &&  !InetAddresses.isInetAddress(request.getIpAddress())) {
            throw new MobiusException(HttpStatus.BAD_REQUEST, "Not a valid IP address");
        }

        if(request.getHostNamePrefix() != null && !request.getHostNamePrefix().matches("[a-zA-Z]+")) {
            throw new MobiusException(HttpStatus.BAD_REQUEST, "Host Name prefix can only contain alphabet characters");
        }

        if(request.getLeaseEnd() == null) {
            throw new MobiusException(HttpStatus.BAD_REQUEST, "No end time specified");
        }
        if(request.getLeaseStart() == null) {
            Date now = new Date();
            long milliseconds = now.getTime()/1000;

            request.setLeaseStart(Long.toString(milliseconds));
        }
        validateLeasTime(request.getLeaseStart(), request.getLeaseEnd(), isFutureRequest, null);
        LOGGER.debug("validateComputeRequest: OUT");
    }

    /*
     * @brief function to process compute request
     *
     * @param request - compute request
     * @param nameIndex - number representing index to be added to instance name
     * @param isFutureRequest - true in case this is a future request; false otherwise
     *
     * @throws Exception in case of error
     *
     * @return number representing index to be added for the instance name
     */
    @Override
    public Pair<Integer, Integer> processCompute(ComputeRequest request, int nameIndex, int spNameIndex, boolean isFutureRequest) throws Exception {
        synchronized (this) {
            LOGGER.debug("processCompute: IN");

            validateComputeRequest(request, isFutureRequest);

            List<String> flavorList = ExogeniFlavorAlgo.determineFlavors(request.getCpus(), request.getRamPerCpus(), request.getDiskPerCpus(), request.isCoallocate());
            if (flavorList == null) {
                throw new MobiusException(HttpStatus.BAD_REQUEST, "None of the flavors can satisfy compute request");
            }

            String sliceName = null;

            switch (request.getSlicePolicy()) {
                case NEW:
                    // Create new slice
                    break;
                case DEFAULT:
                    sliceName = findSlice(request);
                    break;
                case EXISTING:
                    sliceName = request.getSliceName();
                    break;
                default:
                    throw new MobiusException(HttpStatus.BAD_REQUEST, "Unspported SlicePolicy");
            }

            SliceContext context = null;
            boolean addSliceToMaps = false;

            if (sliceName != null) {
                LOGGER.debug("Using existing context=" + sliceName);
                context = sliceContextHashMap.get(sliceName);
            } else {
                context = new SliceContext(sliceName);
                addSliceToMaps = true;
                LOGGER.debug("Created new context=" + sliceName);
            }

            try {
                Pair<Integer, Integer> r = context.processCompute(flavorList, nameIndex, spNameIndex, request);

                sliceName = context.getSliceName();

                if (addSliceToMaps) {

                    Date expiry = context.getExpiry();
                    sliceContextHashMap.put(sliceName, context);
                    if(expiry != null) {
                        leaseEndTimeToSliceNameHashMap.put(expiry, sliceName);
                        LOGGER.debug("Added " + sliceName + " with expiry= " + expiry + " ");
                    }
                }
                return r;
            } catch (SliceNotFoundOrDeadException e) {
                handSliceNotFoundException(context.getSliceName());
                sliceContextHashMap.remove(context);
                throw new MobiusException("Slice not found");
            } finally {
                LOGGER.debug("processCompute: OUT");
            }
        }
    }

    /*
     * @brief function to process storge request
     *
     * @param request - storge request
     * @param nameIndex - number representing index to be added to instance name
     * @param isFutureRequest - true in case this is a future request; false otherwise
     *
     * @throws Exception in case of error
     *
     * @return number representing index to be added for the instance name
     */
    @Override
    public int processStorageRequest(StorageRequest request, int nameIndex, boolean isFutureRequest) throws Exception {
        synchronized (this) {
            LOGGER.debug("processStorageRequest: IN");
            validateLeasTime(request.getLeaseStart(), request.getLeaseEnd(), isFutureRequest, null);

            String sliceName = hostNameToSliceNameHashMap.get(request.getTarget());
            if (sliceName == null) {
                throw new MobiusException("hostName not found in hostNameToSliceHashMap");
            }
            SliceContext context = sliceContextHashMap.get(sliceName);
            if (context == null) {
                throw new MobiusException("slice context not found");
            }
            try {
                nameIndex = context.processStorageRequest(request, nameIndex);
                return nameIndex;
            } catch (SliceNotFoundOrDeadException e) {
                handSliceNotFoundException(context.getSliceName());
                sliceContextHashMap.remove(context);
                throw new MobiusException("Slice not found");
            } finally {
                LOGGER.debug("processStorageRequest: OUT");
            }
        }
    }

    /*
     * @brief function to process a stitch request;
     *
     * @param request - stitch request
     * @param nameIndex - number representing index to be added to instance name
     * @param isFutureRequest - true in case this is a future request; false otherwise
     *
     * @throws Exception in case of error
     *
     * @return number representing index to be added for the instance name
     *
     */
    @Override
    public int processStitchRequest(StitchRequest request, int nameIndex, boolean isFutureRequest) throws Exception {
        synchronized (this) {
            LOGGER.debug("processStitchRequest: IN");

            String sliceName = hostNameToSliceNameHashMap.get(request.getTarget());
            if (sliceName == null) {
                throw new MobiusException("hostName not found in hostNameToSliceHashMap");
            }
            SliceContext context = sliceContextHashMap.get(sliceName);
            if (context == null) {
                throw new MobiusException("slice context not found");
            }
            try {
                nameIndex = context.processStitchRequest(request, nameIndex);
                return nameIndex;
            } catch (SliceNotFoundOrDeadException e) {
                handSliceNotFoundException(context.getSliceName());
                sliceContextHashMap.remove(context);
                throw new MobiusException("Slice not found");
            } finally {
                LOGGER.debug("processStitchRequest: OUT");
            }
        }
    }

    /*
     * @brief function to check get status for the context
     *
     * @return JSONObject representing status
     */
    @Override
    public JSONObject getStatus() throws Exception {
        synchronized (this) {
            LOGGER.debug("getStatus: IN");
            JSONObject retVal = null;
            JSONArray array = new JSONArray();

            SliceContext context = null;
            for (HashMap.Entry<String, SliceContext> entry : sliceContextHashMap.entrySet()) {
                context = entry.getValue();

                try {
                    JSONObject object = context.status(hostNameSet);
                    if (!object.isEmpty()) {
                        array.add(object);
                    }
                } catch (SliceNotFoundOrDeadException e) {
                    handSliceNotFoundException(context.getSliceName());
                    sliceContextHashMap.remove(context);
                }
            }
            if (!array.isEmpty()) {
                retVal = new JSONObject();
                retVal.put(CloudContext.JsonKeySite, getSite());
                retVal.put(CloudContext.JsonKeySlices, array);
            }
            LOGGER.debug("getStatus: OUT");
            return retVal;
        }
    }

    /*
     * @brief function to release all resources associated with this context
     */
    @Override
    public void stop() throws Exception {
        synchronized (this) {
            LOGGER.debug("stop: IN");
            SliceContext context = null;
            for (HashMap.Entry<String, SliceContext> entry : sliceContextHashMap.entrySet()) {
                context = entry.getValue();
                context.stop();
            }
            sliceContextHashMap.clear();
            LOGGER.debug("stop: OUT");
        }
    }

    /*
     * @brief performs following periodic actions
     *        - Reload hostnames of all instances
     *        - Reload hostNameToSliceNameHashMap
     *        - Determine if notification to pegasus should be triggered
     *        - Build notification JSON object
     *
     * @return JSONObject representing notification for context to be sent to pegasus
     */
    @Override
    public JSONObject doPeriodic() {
        synchronized (this) {
            LOGGER.debug("doPeriodic: IN");
            SliceContext context = null;
            JSONObject retVal = null;
            JSONArray array = new JSONArray();
            hostNameToSliceNameHashMap.clear();
            leaseEndTimeToSliceNameHashMap.clear();
            hostNameSet.clear();
            Iterator<HashMap.Entry<String, SliceContext>> iterator = sliceContextHashMap.entrySet().iterator();
            while (iterator.hasNext()) {
                HashMap.Entry<String, SliceContext> entry = iterator.next();
                context = entry.getValue();
                Set<String> hostNames = new HashSet<>();
                JSONObject result = null;
                try {
                    result = context.doPeriodic(hostNames);
                } catch (SliceNotFoundOrDeadException e) {
                    handSliceNotFoundException(context.getSliceName());
                    iterator.remove();
                    continue;
                }
                hostNameSet.addAll(hostNames);
                for (String h : hostNames) {
                    if (!hostNameToSliceNameHashMap.containsKey(h) && context.getSliceName() != null) {
                        hostNameToSliceNameHashMap.put(h, context.getSliceName());
                    }
                }
                if (result != null && !result.isEmpty()) {
                    array.add(result);
                }
                // TODO find a way to reload expiryTime
                if (context.getExpiry() != null) {
                    leaseEndTimeToSliceNameHashMap.put(context.getExpiry(), context.getSliceName());
                }
                triggerNotification |= context.canTriggerNotification();
                if (context.canTriggerNotification()) {
                    context.setSendNotification(false);
                }
            }
            if (!array.isEmpty()) {
                retVal = new JSONObject();
                retVal.put(CloudContext.JsonKeySite, getSite());
                retVal.put(CloudContext.JsonKeySlices, array);
            }

            LOGGER.debug("doPeriodic: OUT");
            return retVal;
        }
    }

    /*
     * @brief function to check if an instance with this hostname exists in this context
     *
     * @return true if hostname exists; false otherwise
     */
    @Override
    public boolean containsSlice(String sliceName) {
        return sliceContextHashMap.containsKey(sliceName);
    }

    /*
     * @brief find slice with lease time if exists
     *
     * @param request - compute request
     *
     * @return slice name
     */
    protected String findSlice(ComputeRequest request) {
        LOGGER.debug("findSlice: IN");
        if(leaseEndTimeToSliceNameHashMap.size() == 0) {
            LOGGER.debug("findSlice: OUT - leaseEndTimeToSliceNameHashMap empty");
            return null;
        }

        if(request.getLeaseEnd() == null) {
            LOGGER.debug("findSlice: OUT - getLeaseEnd null");
            return null;
        }

        long timestamp = Long.parseLong(request.getLeaseEnd());
        Date expiry = new Date(timestamp * 1000);

        String sliceName = null;
        if(leaseEndTimeToSliceNameHashMap.containsKey(expiry)) {
            sliceName = leaseEndTimeToSliceNameHashMap.get(expiry).iterator().next();
        }
        LOGGER.debug("findSlice: OUT");
        return sliceName;
    }

    /*
     * @brief function to handle slice not found
     *
     * @param sliceName - slice name
     */
    protected void handSliceNotFoundException(String sliceName) {
        LOGGER.debug("handSliceNotFoundException: IN");
        if(hostNameToSliceNameHashMap.containsValue(sliceName)) {
            Iterator<HashMap.Entry<String, String>> iterator = hostNameToSliceNameHashMap.entrySet().iterator();
            while (iterator.hasNext()) {
                HashMap.Entry<String, String> entry = iterator.next();
                if(entry.getValue().equalsIgnoreCase(sliceName)) {
                    iterator.remove();
                }
            }
        }
        if(leaseEndTimeToSliceNameHashMap.containsValue(sliceName)) {
            Iterator<Map.Entry<Date, String>> iterator = leaseEndTimeToSliceNameHashMap.entries().iterator();
            while (iterator.hasNext()) {
                Map.Entry<Date, String> entry = iterator.next();
                if(entry.getValue().equalsIgnoreCase(sliceName)) {
                    iterator.remove();
                }
            }
        }
        LOGGER.debug("handSliceNotFoundException: OUT");
    }
}
