import device_pb2, device_pb2_grpc
import grpc
from google.protobuf.json_format import MessageToDict
#from google.protobuf.json_format import MessageToJson



"""
The Starlink WiFi gRPC server is hosted at port 9000. The Starlink router 
uses the 192.168.1.1/24 by default.
"""
STARLINK_ROUTER_GRPC_ADDR = "192.168.1.1:9000"

"""
The Starlink dish gRPC server is hosted at port 9200. The Starlink dish
is always at 192.168.100.1.
"""
STARLINK_DISH_GRPC_ADDR = "192.168.100.1:9200"

"""
Send the GetDiagnostics request to the given address.
"""
def get_diagnostics(addr: str) -> device_pb2.Response:
	with grpc.insecure_channel(addr) as channel:
		return device_pb2_grpc.DeviceStub(channel).Handle(device_pb2.Request(get_diagnostics=device_pb2.GetDiagnosticsRequest()))

'''
print ("Sending request to router...")
try:
	response = get_diagnostics(STARLINK_ROUTER_GRPC_ADDR)
except grpc.RpcError as e:
	print(e.code())
else:
	print(response)
'''


def starlinkTarget(response):
	myDict = MessageToDict(response)
	dVal = str(myDict['dishGetDiagnostics'])
	targetStart = dVal.find('desiredBoresightAzimuthDeg')
	if (targetStart <0):
		return 910
	targetStart = targetStart+29
	targetEnd = targetStart+5
	TARGET = dVal[targetStart:targetEnd]
	print ("STARLINK TARGET = " + str(TARGET))
	return float(TARGET)

def getStarlinkTarget():
	response = getStarlinkDiagnostics()
	if (response == 999):
		return response
	TARGET = starlinkTaarget(response)
	return TARGET


def starlinkCurrent(response):
	myDict = MessageToDict(response)
	dVal = str(myDict['dishGetDiagnostics'])
	currentStart = dVal.find('boresightAzimuthDeg')
	if (currentStart < 0):
		return 920
	currentStart = currentStart+22
	currentEnd = currentStart+5
	CURRENT = dVal[currentStart:currentEnd]
	print ("STARLINK CURRENT = " + str(CURRENT))
	return float(CURRENT)

def getStarlinkCurrent():
	response = getStarlinkDiagnostics()
	if (response == 999):
		return response
	CURRENT = starlinkCurrent(response)
	return CURRENT


def getStarlinkDiff():
	response = getStarlinkDiagnostics()
	if (response == 999):
		return response
	TARGET = starlinkTarget(response)
	if (TARGET == 910):
		return TARGET
	CURRENT = starlinkCurrent(response)
	if (CURRENT == 920):
		return CURRENT
	DIFF = calcDiff(CURRENT, TARGET)
	print ("STARLINK DIFF = " + str(DIFF))
	return float(DIFF)


def getStarlinkDiagnostics():
	print ("****** Sending diagnostic request to dish. Please wait...  *******")
	try:
		response = get_diagnostics(STARLINK_DISH_GRPC_ADDR)
	except grpc.RpcError as e:
		print (e.code())
		print (e)
		return 999
	else:
		print (response)
		return response


def calcDiff(current, target):
        current = float(current)
        target = float(target)
        diff = (current - 360) if current > 180 else current
        diff = target - diff
        if (diff >= 180):
                diff=diff-360
        #return target if target < 180 else target - 360
        print ("Diff Degrees= " + str(int(diff*100)/100) + "*" )
        return diff


#def getStarlinkDiff():
#	return getDiff(CURRENT, TARGET)



#try:
#DIFF = getStarlinkDiff()

#print ("DIFF = " + str(DIFF))
'''
except:
	print ("ERROR")
finally:
	print ("Goodbye from Starlink API")
'''
