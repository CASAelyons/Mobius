#
# Copyright (c) 2017 Renaissance Computing Institute, except where noted.
# All rights reserved.
#
# This software is released under GPLv2
#
# Renaissance Computing Institute,
# (A Joint Institute between the University of North Carolina at Chapel Hill,
# North Carolina State University, and Duke University)
# http://www.renci.org
#
# For questions, comments please contact software@renci.org
#
# Author: Komal Thareja(kthare10@renci.org)

import sys
import os
import time
import json
import argparse
import subprocess
import socket


from mobius import *
from comet_common_iface import *

pubKeysVal={"val_":"[{\"publicKey\":\"\"}]"}
hostNameVal={"val_":"[{\"hostName\":\"REPLACE\",\"ip\":\"IPADDR\"}]"}


def is_valid_ipv4_address(address):
    try:
        socket.inet_pton(socket.AF_INET, address)
    except AttributeError:  # no inet_pton here, sorry
        try:
            socket.inet_aton(address)
        except socket.error:
            return False
        return address.count('.') == 3
    except socket.error:  # not a valid address
        return False

    return True

def can_ip_satisfy_range(ip, n):
    octets = ip.split('.')
    octets[3] = str(int(octets[3]) + n)
    print ("Last IP: " + '.'.join(octets))
    return is_valid_ipv4_address('.'.join(octets))

def get_cidr(ip):
    octets = ip.split('.')
    octets[3] = '0/24'
    print ("CIDR: " + '.'.join(octets))
    return '.'.join(octets)

def get_cidr_escape(ip):
    octets = ip.split('.')
    octets[3] = '0\/24'
    print ("CIDR: " + '.'.join(octets))
    return '.'.join(octets)

def get_default_ip_for_condor(ip):
    octets = ip.split('.')
    octets[3] = '*'
    print ("Default IP: " + '.'.join(octets))
    return '.'.join(octets)

def get_next_ip(ip):
    octets = ip.split('.')
    octets[3] = str(int(octets[3]) + 1)
    print ("Next IP: " + '.'.join(octets))
    return '.'.join(octets)

def main():
    parser = argparse.ArgumentParser(description='Python client to create Condor cluster using mobius.\nUses master.json, submit.json and worker.json for compute requests present in data directory specified.\nCurrently only supports provisioning compute resources. Other resources can be provisioned via mobius_client.\nCreates COMET contexts for Chameleon resources and thus enables exchanging keys and hostnames within workflow')

    parser.add_argument(
        '-s1',
        '--exogenisite',
        dest='exogenisite',
        type = str,
        help='Exogeni Site at which resources must be provisioned; must be specified for create operation',
        required=False
    )
    parser.add_argument(
        '-s2',
        '--chameleonsite',
        dest='chameleonsite',
        type = str,
        help='Chameleon Site at which resources must be provisioned; must be specified for create operation',
        required=False
    )
    parser.add_argument(
        '-n1',
        '--exoworkers',
        dest='exoworkers',
        type = int,
        help='Number of workers to be provisioned on Exogeni; must be specified for create operation',
        required=False
    )
    parser.add_argument(
        '-n2',
        '--chworkers',
        dest='chworkers',
        type = int,
        help='Number of workers to be provisioned on Chameleon; must be specified for create operation',
        required=False
    )
    parser.add_argument(
        '-c',
        '--comethost',
        dest='comethost',
        type = str,
        help='Comet Host e.g. https://18.218.34.48:8111/; used only for provisioning resources on chameleon',
        required=False
    )
    parser.add_argument(
        '-t',
        '--cert',
        dest='cert',
        type = str,
        help='Comet Certificate; used only for provisioning resources on chameleon',
        required=False
    )
    parser.add_argument(
        '-k',
        '--key',
        dest='key',
        type = str,
        help='Comet Certificate key; used only for provisioning resources on chameleon',
        required=False
    )
    parser.add_argument(
        '-m',
        '--mobiushost',
        dest='mobiushost',
        type = str,
        help='Mobius Host e.g. http://localhost:8080/mobius',
        required=False,
        default='http://localhost:8080/mobius'
    )
    parser.add_argument(
       '-o',
       '--operation',
       dest='operation',
       type = str,
       help='Operation allowed values: create|get|delete',
       required=True
    )
    parser.add_argument(
        '-w',
        '--workflowId',
        dest='workflowId',
        type = str,
        help='workflowId',
        required=True
    )
    parser.add_argument(
        '-i1',
        '--exoipStart',
        dest='exoipStart',
        type = str,
        help='Exogeni Start IP Address of the range of IPs to be used for VMs; 1st IP is assigned to master and subsequent IPs are assigned to submit node and workers; can be specified for create operation',
        required=False
    )
    parser.add_argument(
        '-i2',
        '--chipStart',
        dest='chipStart',
        type = str,
        help='Chameleon Start IP Address of the range of IPs to be used for VMs; 1st IP is assigned to master and subsequent IPs are assigned to submit node and workers; can be specified for create operation',
        required=False
    )
    parser.add_argument(
        '-l',
        '--leaseEnd',
        dest='leaseEnd',
        type = str,
        help='Lease End Time; can be specified for create operation',
        required=False
    )
    parser.add_argument(
        '-d1',
        '--exodatadir',
        dest='exodatadir',
        type = str,
        help='Exogeni Data directory where to look for master.json, submit.json and worker.json; must be specified for create operation',
        required=False
    )
    parser.add_argument(
        '-d2',
        '--chdatadir',
        dest='chdatadir',
        type = str,
        help='Chameleon Data directory where to look for master.json, submit.json and worker.json; must be specified for create operation',
        required=False
    )

    args = parser.parse_args()
    mb=MobiusInterface()

    if args.operation == 'get':
        print ("Getting status of workflow")
        response=mb.get_workflow(args.mobiushost, args.workflowId)
    elif args.operation == 'delete':
        print ("Deleting workflow")
        response=mb.delete_workflow(args.mobiushost, args.workflowId)
        if args.comethost is not None:
            print ("Cleaning up COMET context for workflow")
            comet=CometInterface(args.comethost, None, args.cert, args.key, None)
            response=comet.delete_families(args.comethost, args.workflowId, None, args.workflowId, args.workflowId)
    elif args.operation == 'create':
        ipMap = dict()
        if (args.exogenisite is None and args.chameleonsite is None) or (args.exoworkers is None and args.chworkers is None)  or (args.exodatadir is None and args.chdatadir is None) :
            print ("ERROR: site name, number of workers and data directory must be specified for create operation")
            parser.print_help()
            sys.exit(1)
        if args.exoipStart is not None:
            if is_valid_ipv4_address(args.exoipStart) == False :
                print ("ERROR: Invalid start ip address specified")
                parser.print_help()
                sys.exit(1)
            if can_ip_satisfy_range(args.exoipStart, args.exoworkers + 1) == False:
                print ("ERROR: Invalid start ip address specified; cannot accomdate the ip for all nodes")
                parser.print_help()
                sys.exit(1)
        if args.chipStart is not None:
            if is_valid_ipv4_address(args.chipStart) == False :
                print ("ERROR: Invalid start ip address specified")
                parser.print_help()
                sys.exit(1)
            if can_ip_satisfy_range(args.chipStart, args.chworkers + 1) == False:
                print ("ERROR: Invalid start ip address specified; cannot accomdate the ip for all nodes")
                parser.print_help()
                sys.exit(1)
        if args.comethost is not None:
            if args.cert is None or args.key is None:
                print ("ERROR: comet certificate and key must be specified when comethost is indicated")
                parser.print_help()
                sys.exit(1)
        if args.chameleonsite is not None :
            if "Chameleon" not in args.chameleonsite :
                print ("ERROR: Invalid site specified")
                parser.print_help()
                sys.exit(1)
        if args.exogenisite is not None :
            if "Exogeni" not in args.exogenisite :
                print ("ERROR: Invalid site specified")
                parser.print_help()
                sys.exit(1)

        print ("Creating workflow")
        response=mb.create_workflow(args.mobiushost, args.workflowId)
        count = 0
        stitchdata = None
        chstoragename = None
        exostoragename = None
        if response.json()["status"] == 200:
            submitSubnet=None
            sip=None
            # Determine Stitching IP for storage node to be used for configuring routes on chameleon
            if args.exogenisite is not None and args.exodatadir is not None:
                d = args.exodatadir + "/stitch.json"
                if os.path.exists(d) :
                    d_f = open(d, 'r')
                    stitchdata = json.load(d_f)
                    d_f.close()
                    sip = stitchdata["stitchIP"]
                d = args.exodatadir + "/storage.json"
                if os.path.exists(d) :
                    d_f = open(d, 'r')
                    submitdata = json.load(d_f)
                    d_f.close()
                    ip= submitdata["stitchIP"]
                    print("KOMAL debug: " + str(ip))
                    submitSubnet = get_cidr(ip)
            if args.chameleonsite is not None and args.chdatadir is not None:
                exogeniSubnet = None
                if args.exoipStart is not None:
                    exogeniSubnet = get_cidr(args.exoipStart)
                status, count, chstoragename = provision_storage(args, args.chdatadir, args.chameleonsite, ipMap, count, args.chipStart, submitSubnet, None, exogeniSubnet)
                if status == False:
                    return
                chstoragename = chstoragename + ".novalocal"
            if args.exogenisite is not None and args.exodatadir is not None:
                status, count, exostoragename = provision_storage(args, args.exodatadir, args.exogenisite, ipMap, count, args.exoipStart, submitSubnet, sip)
                if status == False :
                    return
            if args.chameleonsite is not None and args.chdatadir is not None:
                exogeniSubnet = None
                if args.exoipStart is not None:
                    exogeniSubnet = get_cidr(args.exoipStart)
                forwardIP = None
                if stitchdata is not None:
                    forwardIP = stitchdata["stitchIP"]
                status, count = provision_condor_cluster(args, args.chdatadir, args.chameleonsite, ipMap, count, args.chipStart, args.chworkers, chstoragename, exogeniSubnet, forwardIP, submitSubnet)
                if status == False:
                    return
                print ("ipMap after chameleon: "  + str(ipMap))
            if args.exogenisite is not None and args.exodatadir is not None:
                #d = args.exodatadir + "/stitch.json"
                #if os.path.exists(d) and args.chipStart is not None:
                #    print ("Using " + d + " file for stitch data under exogeni " + args.chipStart)
                #    d_f = open(d, 'r')
                #    stitchdata = json.load(d_f)
                #    d_f.close()
                    ### To be uncomented if needed
                    #if args.chipStart is not None :
                    #    i = 0
                    #    sip = args.chipStart
                    #    while i <= count :
                    #        sip = get_next_ip(sip)
                    #        i = i + 1
                    #    stitchdata["stitchIP"] = sip
                chSubnet = None
                forwardIP = None
                if args.chipStart is not None:
                    chSubnet = get_cidr(args.chipStart)
                if exostoragename is not None:
                    forwardIP = ipMap[exostoragename]
                status, count = provision_condor_cluster(args, args.exodatadir, args.exogenisite, ipMap, count, args.exoipStart, args.exoworkers, exostoragename, chSubnet, forwardIP, submitSubnet)
                if status == False :
                    return
                print ("ipMap after exogeni: "  + str(ipMap))
            response=mb.get_workflow(args.mobiushost, args.workflowId)
            stitcVlanToChameleon = None
            if response.json()["status"] == 200 and args.comethost is not None:
                print ("Setting up COMET for exchanging host names and keys")
                comet=CometInterface(args.comethost, None, args.cert, args.key, None)
                readToken=args.workflowId + "read"
                writeToken=args.workflowId + "write"
                status=json.loads(response.json()["value"])
                requests = json.loads(status["workflowStatus"])
                stitchNodeStatus = None
                for req in requests:
                    if "Chameleon" in req["site"] :
                        if "vlan" in req:
                            stitcVlanToChameleon = str(req["vlan"])
                    slices = req["slices"]
                    for s in slices:
                        nodes = s["nodes"]
                        for n in nodes :
                            print ("Create comet context for node " + n["name"])
                            response=comet.update_family(args.comethost, args.workflowId, n["name"],
                                    readToken, writeToken, "pubkeysall", pubKeysVal)
                            print ("Received Response Status Code: " + str(response.status_code))
                            print ("Received Response Message: " + response.json()["message"])
                            print ("Received Response Status: " + response.json()["status"])
                            if response.status_code == 200 :
                                print ("Received Response Value: " + str(response.json()["value"]))

                            hostVal = json.dumps(hostNameVal)
                            if "Chameleon" in s["slice"] :
                                hostname=n["name"] + ".novalocal"
                            else :
                                hostname=n["name"]
                                if stitchdata is not None :
                                    if stitchdata["target"] in n["name"]:
                                        print ("Updating target in exogeni stitch request")
                                        stitchdata["target"]=n["name"]
                                        stitchNodeStatus = n["state"]
                            hostVal = hostVal.replace("REPLACE", hostname)
                            if n["name"] in ipMap:
                                print ("Replacing IPADDR with " + ipMap[n["name"]])
                                hostVal = hostVal.replace("IPADDR", ipMap[n["name"]])
                                #if stitchdata["target"] == n["name"] :
                                #    print ("Replacing IPADDR with " + stitchdata["stitchIP"])
                                #    hostVal = hostVal.replace("IPADDR", stitchdata["stitchIP"])
                            else:
                                print ("Replacing IPADDR with empty string")
                                hostVal = hostVal.replace("IPADDR", "")
                            val = json.loads(hostVal)
                            response=comet.update_family(args.comethost, args.workflowId, n["name"],
                                    readToken, writeToken, "hostsall", val)
                            print ("Received Response Status Code: " + str(response.status_code))
                            print ("Received Response Message: " + response.json()["message"])
                            print ("Received Response Status: " + response.json()["status"])
                            if response.status_code == 200 :
                                print ("Received Response Value: " + str(response.json()["value"]))
            if stitcVlanToChameleon is not None and args.exogenisite is not None:
                while stitchNodeStatus != "Active" :
                    print ("Waiting for the " + stitchdata["target"] + " to become active")
                    response=mb.get_workflow(args.mobiushost, args.workflowId)
                    if response.json()["status"] == 200 :
                        status=json.loads(response.json()["value"])
                        requests = json.loads(status["workflowStatus"])
                        for req in requests:
                            if "Exogeni" in req["site"] :
                                slices = req["slices"]
                                for s in slices:
                                    nodes = s["nodes"]
                                    for n in nodes :
                                        if stitchdata["target"] == n["name"] :
                                            print ("Updating state of " + stitchdata["target"])
                                            stitchNodeStatus = n["state"]
                    print ("Sleeping for 5 seconds")
                    time.sleep(5)
                time.sleep(60)

                print ("stitcVlanToChameleon = " + stitcVlanToChameleon)
                print ("perform stitching")
                perform_stitch(mb, args, args.exodatadir, args.exogenisite, stitcVlanToChameleon, stitchdata)
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0)

def perform_stitch(mb, args, datadir, site, vlan, data):
    if data is None :
        d = datadir + "/stitch.json"
        if os.path.exists(d):
            print ("Using " + d + " file for stitch data")
            d_f = open(d, 'r')
            data = json.load(d_f)
            d_f.close()
    if data is not None:
        data["tag"] = vlan
        print ("payload for stitch request" + str(data))
        response=mb.create_stitchport(args.mobiushost, args.workflowId, data)
        return response

def provision_storage(args, datadir, site, ipMap, count, ipStart, submitSubnet, sip=None, exogeniSubnet=None):
    stdata = None
    st = datadir + "/storage.json"
    if os.path.exists(st):
        print ("Using " + st + " file for compute storage data")
        st_f = open(st, 'r')
        stdata = json.load(st_f)
        st_f.close()
        stdata["site"]=site

    if stdata is None:
        return True, count, None

    if stdata["postBootScript"] is not None :
        cidr=get_cidr_escape(ipStart)
        s=stdata["postBootScript"]
        s=s.replace("CIDR",cidr)
        if sip is not None:
            s=s.replace("SIP", str(sip))
        stdata["postBootScript"] = s

    mb=MobiusInterface()
    if stdata is not None :
        print ("Provisioning compute storage node")
        nodename="Node" + str(count)
        oldnodename = "NODENAME"
        response, nodename = create_compute(mb, args.mobiushost, nodename, ipStart, args.leaseEnd, args.workflowId, stdata, count, ipMap, oldnodename, site, submitSubnet, None, exogeniSubnet)
        print (nodename + " after create_compute")
        if response.json()["status"] != 200:
            print ("Deleting workflow")
            response=mb.delete_workflow(args.mobiushost, args.workflowId)
            return False, count, None
        count = count + 1
    return True, count, nodename

def provision_condor_cluster(args, datadir, site, ipMap, count, ipStart, workers, storagename, subnet, forwardIP, submitSubnet):
    mdata = None
    sdata = None
    wdata = None
    m = datadir + "/master.json"
    s = datadir + "/submit.json"
    w = datadir + "/worker.json"
    if os.path.exists(m):
        print ("Using " + m + " file for master data")
        m_f = open(m, 'r')
        mdata = json.load(m_f)
        m_f.close()
        mdata["site"]=site
    if os.path.exists(s):
        print ("Using " + s + " file for submit data")
        s_f = open(s, 'r')
        sdata = json.load(s_f)
        s_f.close()
        sdata["site"]=site
    if os.path.exists(w):
        print ("Using " + w + " file for worker data")
        w_f = open(w, 'r')
        wdata = json.load(w_f)
        w_f.close()
        wdata["site"]=site

    mb=MobiusInterface()
    if mdata is not None :
        print ("Provisioning master node")
        nodename="Node" + str(count)
        oldnodename = "NODENAME"
        if ipStart is not None and storagename is not None:
            ipStart = get_next_ip(ipStart)
        response, nodename = create_compute(mb, args.mobiushost, nodename, ipStart, args.leaseEnd, args.workflowId, mdata, count, ipMap, oldnodename, site, submitSubnet, storagename, subnet, forwardIP)
        print (nodename + " after create_compute")
        if response.json()["status"] != 200:
            print ("Deleting workflow")
            response=mb.delete_workflow(args.mobiushost, args.workflowId)
            return False, count
        count = count + 1
    if sdata is not None :
        print ("Provisioning submit node")
        nodename="Node" + str(count)
        oldnodename = "NODENAME"
        if ipStart is not None :
            ipStart = get_next_ip(ipStart)
        response, nodename = create_compute(mb, args.mobiushost, nodename, ipStart, args.leaseEnd, args.workflowId, sdata, count, ipMap, oldnodename, site, submitSubnet, storagename, subnet, forwardIP)
        print (nodename + " after create_compute")
        if response.json()["status"] != 200:
            print ("Deleting workflow")
            response=mb.delete_workflow(args.mobiushost, args.workflowId)
            return False, count
        count = count + 1
    if wdata is not None :
        oldnodename = "NODENAME"
        for x in range(workers):
            print ("Provisioning worker: " + str(x))
            nodename="Node" + str(count)
            if ipStart is not None :
                ipStart = get_next_ip(ipStart)
            response, nodename = create_compute(mb, args.mobiushost, nodename, ipStart, args.leaseEnd, args.workflowId, wdata, count, ipMap, oldnodename, site, submitSubnet, storagename, subnet, forwardIP)
            print (nodename + " after create_compute")
            oldnodename = nodename
            if response.json()["status"] != 200:
                print ("Deleting workflow")
                response=mb.delete_workflow(args.mobiushost, args.workflowId)
                return False, count
            count = count + 1
    return True, count

def create_compute(mb, host, nodename, ipStart, leaseEnd, workflowId, mdata, count, ipMap, oldnodename, site, submitSubnet, storagename=None, subnet=None, forwardIP=None):
    if mdata["hostNamePrefix"] is not None :
        if "Exogeni" in site:
            nodename = mdata["hostNamePrefix"] + str(count)
        else :
            nodename = workflowId + "-" + mdata["hostNamePrefix"] + str(count)
    defIP = None
    if ipStart is not None :
        mdata["ipAddress"] = ipStart
        ipMap[nodename] = ipStart
        print ("Setting " + nodename + " to " + ipStart)
        defIP = get_default_ip_for_condor(ipStart)
    if leaseEnd is not None:
        print ("Setting leaseEnd to " + leaseEnd)
        mdata["leaseEnd"] = leaseEnd
    if mdata["postBootScript"] is not None:
        s=mdata["postBootScript"]
        s=s.replace("WORKFLOW", workflowId)
        s=s.replace(oldnodename, nodename)
        s=s.replace("SUBMIT", str(submitSubnet))
        print ("replacing " + oldnodename + " to " + nodename)
        if forwardIP is not None:
            s=s.replace("IPADDR", forwardIP)
            if subnet != None:
                s=s.replace("SUBNET", subnet)
        if ipStart is not None :
            s=s.replace("IPADDR", ipStart)
            if subnet != None:
                s=s.replace("SUBNET", subnet)
        if defIP is not None:
            s=s.replace("REPLACEIP", defIP)
        if storagename is not  None:
            s=s.replace("STORAGENODE", storagename)
        mdata["postBootScript"]=s
        print("==========================================================")
        print ("postBootScript: " + str(mdata["postBootScript"]))
        print("==========================================================")
    response=mb.create_compute(host, workflowId, mdata)
    return response, nodename

if __name__ == '__main__':
    main()
