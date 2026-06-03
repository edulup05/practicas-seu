from PicoAutonomousRobotics import KitronikPicoRobotBuggy
from time import sleep_ms

buggy = KitronikPicoRobotBuggy()

buggy.soundFrequency(1000)
buggy.motorOn("l", "f", 30)
buggy.motorOn("r", "f", 30)

while True:
    sleep_ms(100)