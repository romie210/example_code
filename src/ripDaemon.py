import os.path
import socket
import select
import time
import threading
import sys
from random import uniform
from ripPacket import RipPacket
from copy import deepcopy
import random
'''
This is a simplified implementation of the RIP Routing Daemon.
It reads from a config file to instantiate the router, and the 
current implementation is designed to run multiple routers on 
the same computer by assigning different ports.

The select method has been used to listen to multiple ports, and a 
time out of 1 second has been put on to ensure that timers are at 
least updated once per second. This ensures threading is not used, 
as the precise accuracy of the timers is not critical, it is not of
importance that the timers may be out by a small amount of seconds
'''

UDP_IP = "127.0.0.1"
triggered_update_blocking = False
triggered_update_queued = False
router = None

class Router():
    '''
    Router object holds all of the information about the specific router.
    The routing table, neighbour information, input ports, and all timer 
    information is held in this object. Only one router object is created.
    '''
    def __init__(self, ID, input_ports, outputs, timers):
        '''
        Initialises the router object. Takes in the router ID, Input ports,
        neighbour information, and timer information read in from the config file
        '''
        self.ID = ID 
        self.input_ports = input_ports #List of input ports
        self.outputs = outputs #Dictionary of neighbour information
        self.routing_table = {ID: {'Metric': 0,
                                   'NextHop': ID,
                                   'RouteChangeFlag': False,
                                   'Timer': 0}}
        self.scheduled_timer_period = timers[0]
        self.timeout_period = timers[1]
        self.garbage_collection_period = timers[2]
        self.garbage_bin = {}

        self.scheduled_timer = 0
        self.next_scheduled_update = self.scheduled_timer_period

        self.triggered_update_block_time = 0
        self.triggered_update_timer = 0
        self.triggered_update_blocking = False
        self.triggered_update_queued = False

        self.out_socket = None

'''Init Functions'''
#----------------------------------------------------------------------#
def readFile(file):
    '''Function to read a config file in'''
    lines = []
    with open(file) as open_file:
        for line in open_file:
            lines.append(line)
    return lines
            
def processConfigInfo(config_file):
    '''
    Function to process the information from a config file, and check that
    all the config information given is within correct bounds
    '''
    rawinput = readFile(config_file)
    processed_input = []
    for line in rawinput:
        processed_input.append(line.replace(",","").rstrip().split())
    
    if processed_input[0][0] != 'router-id':
        raise Exception, "Could not find router IDs"
    if processed_input[1][0] != 'input-ports':
        raise Exception, "Could not find input ports"     
    if processed_input[2][0] != 'outputs':
        raise Exception, "Could not find outputs"   
    
    router_id = int(processed_input[0][1])
    if router_id > 64000:
        raise Exception, "Router ID value is too large" 
    if router_id < 1:
        raise Exception, "Router ID value is too small"     
    
    router_input_ports = []
    for iport in processed_input[1][1:]:
        if int(iport) > 64000:
            raise Exception, "A router input port number is too large"
        if int(iport) < 1024:
            raise Exception, "A router input port number is too small"        
        router_input_ports.append(int(iport))
        
    router_outputs = {}
    for out in processed_input[2][1:]:
        neighbour_info = {}
        neighbour_list = out.split("-")
        if int(neighbour_list[0]) > 64000:
            raise Exception, "A router output port number is too large"
        if int(neighbour_list[0]) < 1024:
            raise Exception, "A router output port number is too small"
        neighbour_info['Outport'] = int(neighbour_list[0])
        if int(neighbour_list[1]) < 0:
            raise Exception, "A neighbour has a negative metric"        
        neighbour_info['Metric'] = int(neighbour_list[1])
        if int(neighbour_list[2]) > 64000:
            raise Exception, "A neighbour router ID value is too large" 
        if int(neighbour_list[2]) < 1:
            raise Exception, "A neighbour router ID value is too small"           
        router_outputs[int(neighbour_list[2])] = neighbour_info
        
    router_timers = []
    for timer in processed_input[3][1:]:
        router_timers.append(int(timer))
    if int(router_timers[0]) * 6 != int(router_timers[1]):
        raise Exception, "First or second timer value is incorrect" 
    if int(router_timers[0]) * 4 != int(router_timers[2]):
        raise Exception, "First or third timer value is incorrect"        
        

    this_router = Router(router_id, router_input_ports, router_outputs, router_timers)
    print(this_router.outputs)

    return this_router

def initialiseRouter():
    '''Get config file name from stdin'''
    file_read = False

    while not file_read:
        config_file = raw_input('Please enter config file name: ')
        try:
            open(config_file)
        except IOError:
            print("File doesn't exist, try again")
            continue
        else:
            router = processConfigInfo(config_file)
            file_read = True
    return router

def initialiseSockets(input_ports):
    '''Create sockets given from config file'''
    global UDP_IP
    sockets = []

    for port in input_ports:
        addr = (UDP_IP, port)
        input_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        input_socket.bind(addr)
        sockets.append(input_socket)

    return sockets


'''Packet Functions'''
#----------------------------------------------------------------------#
def processRipPacket(socket):
    '''Process the rip packet received over the wire'''
    global router

    data,addr = socket.recvfrom(8000)

    my_bytes = bytearray(data)
    packet = RipPacket()
    packet.fromBytes(my_bytes)

    updateRoutingTable(packet)
    for destinationID in router.routing_table: 
        resetTimeoutTimer(destinationID, packet)

    print("--------------------ROUTING TABLE UPDATED--------------------")
    print("Source: " + str(packet.routerID))
    for destination, information in router.routing_table.iteritems():
        print("Destination: " + str(destination))
        print("Information: " + str(information))

'''Update Functions'''
#----------------------------------------------------------------------#
def scheduledUpdate():
    '''
    Perform a scheduled update, sending packets to all neighbours
    with poisoned reverse to avoid loops.
    '''
    global router

    print "Update going out now"

    timer_value = uniform(0.8, 1.2) * router.scheduled_timer_period
    router.next_scheduled_update = timer_value

    for neighbour_id, neighbour_info in router.outputs.iteritems():
        routing_info = deepcopy(router.routing_table)
        for dest_id, dest_info in routing_info.iteritems():
            if dest_info['NextHop'] == neighbour_id:
                routing_info[dest_id]['Metric'] = 16
                
        ripPacket = RipPacket().toBytes(router.ID, routing_info)
        router.out_socket.sendto(ripPacket, (UDP_IP, neighbour_info['Outport']))

def triggeredUpdate():
    '''
    Perform a triggered update. This implementation only triggers an update
    on routing information timing out, or on receiving 16 as a metric. 
    '''
    global router

    update_info = {}

    triggered_update_queued = False

    print "Triggered update going out"
    for dest_id, dest_info in router.routing_table.iteritems():
        if dest_info['RouteChangeFlag'] == True:
            update_info[dest_id] = dest_info
            router.routing_table[dest_id]['RouteChangeFlag'] = False

    for neighbour_id, neighbour_info in router.outputs.iteritems():
        routing_info = deepcopy(update_info)

        for dest_id, dest_info in routing_info.iteritems():
            if dest_info['NextHop'] == neighbour_id:
                routing_info[dest_id]['Metric'] = 16
        ripPacket = RipPacket().toBytes(router.ID, routing_info)
        router.out_socket.sendto(ripPacket, (UDP_IP, neighbour_info['Outport']))

    router.triggered_update_block_time = random.uniform(1,5)
    router.triggered_update_blocked = True

def triggeredUpdateBlockingEnd():
    '''Called when the timer for blocking triggered updates expires'''
    global router

    router.triggered_update_blocking = False

    if router.triggered_update_queued:
        triggeredUpdate()

def processTriggeredUpdate():
    '''
    Called if a triggered update is wanting to be sent. If there is a
    block in place, flags for one to be queued'''
    global router

    if router.triggered_update_blocking:
        router.triggered_update_queued = True
    else:
        triggeredUpdate()

'''Distance Vector Algorithm Functions'''
#----------------------------------------------------------------------#

def reuseGarbage(destinationID):
    '''
    Called if a routing entry is in garbage collection, and a new entry for
    that router is received.
    '''
    global router

    router.garbage_bin.pop(destinationID, None)

def collectGarbage(destinationID):
    '''
    Called when the gargage collection timeout occurs for an entry which is 
    marked for garbage collection.
    '''
    global router

    print "-------------------Collecting the Trash----------------------------"
    print destinationID
    router.garbage_bin.pop(destinationID, None)
    router.routing_table.pop(destinationID, None)

def addGarbage(destinationID):
    '''
    Called to add a given entry in the routing table to the garbage collection
    process
    '''
    global router

    router.garbage_bin[destinationID] = 0

def shouldRouteChange(current_destinationID_metric, received_destinationID_metric, nexthop, originatingID):
    '''Determines whether the given routing table entry should be udpated with new information'''
    if (int(received_destinationID_metric) < int(current_destinationID_metric)):
        return True
    if (int(received_destinationID_metric) > int(current_destinationID_metric) and nexthop == originatingID):
        return True

def updateRoutingTable(rip_packet):
    '''Entry point in to the DVA. Updates routing table based on packet info'''
    global router

    originatingID = rip_packet.routerID
    
    for destinationID, cost in rip_packet.rtePayloads.iteritems():
        current_destinationID_metric = 16 #From the specification, if metric is > 16, use 16
        nexthop = None

        destinationID = int(destinationID)

        if (destinationID in router.routing_table):
            nexthop = router.routing_table[destinationID]['NextHop']
            current_destinationID_metric = int(router.routing_table[destinationID]['Metric'])

        received_destinationID_metric = min((int(router.outputs[originatingID]['Metric']) + int(cost)), 16)

        if (shouldRouteChange(current_destinationID_metric, received_destinationID_metric, nexthop, originatingID)):
            new_route = {'Metric': received_destinationID_metric,
                         'NextHop': originatingID,
                         'RouteChangeFlag': True,
                         'Timer': 0}
            if destinationID in router.garbage_bin:
                reuseGarbage(router, destinationID)
                router.routing_table[destinationID] = new_route
                router.routing_table[destinationID]['Timers'] = 0

            elif received_destinationID_metric == 16:
                addGarbage(destinationID)
                processTriggeredUpdate()   

                router.routing_table[destinationID] = new_route
                router.routing_table[destinationID]['Timers'] = 0
                
            else:
                router.routing_table[destinationID] = new_route
                router.routing_table[destinationID]['Timers'] = 0


'''Timer Functions'''
#----------------------------------------------------------------------#
def resetTimeoutTimer(destinationID, packet):
    '''
    Called to reset the timer on a routing entry if a packet is received from
    the next hop
    '''
    global router
    if router.routing_table[destinationID]['NextHop'] == packet.routerID:
        router.routing_table[destinationID]['Timer'] = 0

def updateTimers():
    '''Called at least once a second to increase all timers.'''
    global router

    router.scheduled_timer += 1

    for destinationID in router.routing_table:
        router.routing_table[destinationID]['Timer'] += 1
    for destinationID in router.garbage_bin:
        router.garbage_bin['Timer'] += 1
    if router.triggered_update_blocking:
        router.triggered_update_timeout += 1

    router.routing_table[router.ID]['Timer'] = 0


def checkTimeouts():
    '''Called to check if any timers have expired'''
    global router

    for destinationID in router.routing_table:
        if router.routing_table[destinationID]['Timer'] >= router.timeout_period:
            if destinationID not in router.garbage_bin:
                addGarbage(destinationID)
                router.routing_table[destinationID]['Metric'] = 16
                router.routing_table[destinationID]['RouteChangeFlag'] = True
                processTriggeredUpdate()

    if router.scheduled_timer >= router.next_scheduled_update:
        router.scheduled_timer = 0
        scheduledUpdate()

    if router.triggered_update_blocking and router.triggered_update_timeout >= router.triggered_update_block_time:
        triggeredUpdateBlockingEnd()

def main():
    #Initialise
    global router
    router = initialiseRouter()
    in_sockets = initialiseSockets(router.input_ports)
    router.out_socket = in_sockets[0]

    scheduledUpdate()

    '''Main loop'''
    while True:
        readable, _, _ = select.select(in_sockets, [], [], 1)
        for s in readable:
            if s in in_sockets:
                processRipPacket(s)

        updateTimers()
        checkTimeouts()


if __name__ == "__main__":
    main()
    
