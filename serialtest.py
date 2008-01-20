import xmodem
import serial
import sys

print "Clearing serial line"


print "Cleared serial line"

x = xmodem.XModemCRC(debug="stdout")

if sys.argv[1] == "recv":
    p = serial.Serial(port="/dev/ttyS0", baudrate=115200, timeout=2)
    print p.portstr
    p.read(200)
    x.recv_xfer(p)
    o = file("output", "w")
    o.write(x.data)
elif sys.argv[1] == "send":
    p = serial.Serial(port="/dev/ttyUSB0", baudrate=115200, timeout=2)
    print p.portstr
    p.read(200)
    i = file("xmodem.py")
    x.send_xfer(p, i)

