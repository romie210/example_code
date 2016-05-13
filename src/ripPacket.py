import struct

class RipPacket:
    '''Class to decode, and encode Rip Packets'''
    defaultCommand = 2
    defaultVersion = 2
    defaultFamilyIdent = 2
    headerLength = 4
    rteLength = 20
    
    def __init__(self):
        self.rtePayloads = {}

    def fromBytes(self, array):
        '''
        Takes in a byte array. Decodes and returns a RipPacket object,
        with all necessary fields filled out. Ensures that no byte 
        manipulation has to happen after this step, and the fields of the
        object can just be accessed
        '''
        self.rtePayloads = {}
        length = len(array)
        assert((length - self.headerLength) % self.rteLength == 0)
        self.rteNumber = (length - self.headerLength) // self.rteLength
        #RIP HEADER
        self.command = array[0]
        assert(self.command == self.defaultCommand)
        self.version = array[1]
        assert(self.version == self.defaultVersion)
        self.routerID = struct.unpack(">H", array[2:4])[0]

        #RIP RTE's
        for i in range(0, self.rteNumber):
            shift = i * 20
            rte = array[shift + 4:shift + 24]
            #Check Family Identifier is 2
            assert(struct.unpack(">H", rte[0:2])[0] == self.defaultFamilyIdent)
            #Must be 0
            assert(struct.unpack(">H", rte[2:4])[0] == 0)
            destAddr = struct.unpack(">I", rte[4:8])[0]
            #Must be 0
            assert(struct.unpack(">I", rte[8:12])[0] == 0)
            #Must be 0
            assert(struct.unpack(">I", rte[12:16])[0] == 0)            
            metric = struct.unpack(">I", rte[16:20])[0]
            self.rtePayloads[destAddr] = metric

    def toBytes(self, routerID, forwardingEntries):
        '''
        Takes in a routerID, and the routing table
        and constructs a RipPacket and returns a 
        byte array ready to be sent over the wire
        '''
        #RIP Header
        ripPacket = bytearray()

        ripHeader = bytearray(4)
        ripHeader[0] = self.defaultCommand
        ripHeader[1] = self.defaultVersion 

        srcAddr = struct.pack(">H", routerID)

        ripHeader[2] = srcAddr[0]
        ripHeader[3] = srcAddr[1]

        ripPacket = ripHeader

        #RIP RTE Entries
        for key, value in forwardingEntries.iteritems():
            rteEntry = bytearray(20)
            familyIdentifier = struct.pack(">H", self.defaultFamilyIdent)

            rteEntry[0] = familyIdentifier[0]
            rteEntry[1] = familyIdentifier[1]

            destAddr = struct.pack(">I", key)

            rteEntry[4] = destAddr[0]
            rteEntry[5] = destAddr[1]
            rteEntry[6] = destAddr[2]
            rteEntry[7] = destAddr[3]

            metric = struct.pack(">I", value["Metric"])

            rteEntry[16] = metric[0]
            rteEntry[17] = metric[1]
            rteEntry[18] = metric[2]
            rteEntry[19] = metric[3]

            ripPacket = ripPacket + rteEntry

        return ripPacket





















