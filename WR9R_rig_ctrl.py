#
# WR9R Auto Band Switch Manager
# Designed to work with KAT500/KAP500 power Trio and WR9R Antenna Selector
# This will automatically select the antenna based on band selected
# in the N3FJP Logging Softwaare
# 04-04-2024   Larry D O'Cull    WR9R
# 11-27-2024  -- Added retrys to telnet and http connections to stablize the system
# 11-29-2024  -- added display window

import tkinter as tk
from tkinter import ttk
import serial
import requests
import time
import winsound
import asyncio
import threading
import re

MY_AUTOTUNE_ENABLE = "Y"    # Y = Enabled (Elecraft K3) --  Otherwise, radio doesn't matter.

MY_VERSION = "WR9R  V2.a"
MY_SWITCH_URL = "http://192.168.1.179/"
MY_K3_COMM_PORT = "COM4"
MY_KAT500_COMM_PORT = "COM13"
MY_COMM_RATE = "38400"
MY_N3FJP_HOST = "localhost"
MY_N3FJP_PORT = 1100

## This is the WR9R K3-KAT500-WifiRemote Switching Antenna operating situation

band_LUT = [
# K3_string, switch_pos, tune_secs, KAT500_string
    [b'BN00',   "FIVE",    0,  b'AN3;MDB;', "160M", 160],   #160M   Dummy load for safety
    [b'BN01',   "THREE",   4,  b'AN2;MDA;',  "80M", 80],    # 80M   Vertical / Dipole (ANT1/ANT2)
    [b'BN02',   "THREE",   4,  b'AN2;MDA;',  "60M", 60],    # 60M   Vertical / Dipole (ANT1/ANT2)
    [b'BN03',   "THREE",   4,  b'AN2;MDA;',  "40M", 40],    # 40M   Vertical / Dipole (ANT1/ANT2)
    [b'BN04',   "ONE",     4,  b'AN1;MDM;',  "30M", 30],    # 30M   Vertical (KAT500 mop up on match)
    [b'BN05',   "TWO",     1,  b'AN2;MDA;',  "20M", 20],    # 20M   Vertical / HexBeam (ANT1/ANT2)
#    [b'BN06',   "ONE",     4,  b'AN1;MDM;',  "17M", 17],    # 17M   HexBeam  / HexBeam (ANT1/ANT2)
    [b'BN06',   "THREE",   4,  b'AN2;MDA;',  "17M", 17],    # 17M   HexBeam  / HexBeam (ANT1/ANT2)
    [b'BN07',   "TWO",     1,  b'AN2;MDA;',  "15M", 15],    # 15M   HexBeam  / HexBeam (ANT1/ANT2)
#    [b'BN08',   "ONE",     4,  b'AN1;MDM;',  "12M", 12],    # 12M   HexBeam  / HexBeam (ANT1/ANT2)
    [b'BN08',   "THREE",   4,  b'AN2;MDA;',  "12M", 12],    # 12M   HexBeam  / HexBeam (ANT1/ANT2)
    [b'BN09',   "TWO",     1,  b'AN2;MDA;',  "10M", 10],    # 10M   HexBeam  / HexBeam (ANT1/ANT2)
    [b'BN10',   "THREE",   1,  b'AN2;MDA;',  "6M",   6]     #  6M   HexBeam (Dipole avaiable on WR9R-THREE)
]
# other possibilities..
#    [b'BN01',   "THREE",   8,  b'AN2;MDM;T;'],  # 75M   Dipole tough-tune for 75M
#    [b'BN01',   "THREE",   4,  b'AN1;MDB;'],    # 80M   Vertical
#    [b'BN02',   "THREE",   5,  b'AN2;MDM;T;'],  # 60M   Dipole
#    [b'BN05',   "TWO",     3,  b'AN1;MDB;'],    # 20M   Vertical

url = MY_SWITCH_URL
tunerConfig = b''
tuningTime = 0
last_data = b''
bandName = ""
freq = 0
last_freq = 0
last_band = 0
band = 0
KAT500ser = ""
K3ser = ""
TuneTimer = 0

# Global variables for GUI updates
bandName = "N/A"
freqDisplay = "N/A"
switch_position = "N/A"
tuner_setting = "N/A"

# Tkinter GUI setup
def draw_window():
    """Creates the Tkinter GUI."""
    root = tk.Tk()
    root.title("WR9R - N3FJP Antenna Manager")
    root.geometry("400x200")
    # Set the window to stay on top
    root.wm_attributes("-topmost", True)

    # Define a function to terminate the script
    def on_close():
        print("Window closed. Exiting...")
        root.destroy()  # Closes the Tkinter window
        WR9R_shutdown() # Ensures the script terminates

    # Bind the close event to the on_close function
    root.protocol("WM_DELETE_WINDOW", on_close)

    # Configure dark theme
    style = ttk.Style()
    style.configure("TLabel", background="#2D2D2D", foreground="#FFFFFF", font=("Arial", 12))
    style.configure("TFrame", background="#2D2D2D")
    style.configure("TButton", background="#333333", foreground="#FFFFFF")
    root.configure(bg="#2D2D2D")

    # Define labels for Band, Frequency, and Switch Position
    ttk.Label(root, text="Band:", font=("Arial", 12)).grid(row=0, column=0, sticky=tk.W, padx=10, pady=10)
    ttk.Label(root, text="Frequency:", font=("Arial", 12)).grid(row=1, column=0, sticky=tk.W, padx=10, pady=10)
    ttk.Label(root, text="Switch Position:", font=("Arial", 12)).grid(row=2, column=0, sticky=tk.W, padx=10, pady=10)
    ttk.Label(root, text="Tuner Setting:", font=("Arial", 12)).grid(row=3, column=0, sticky=tk.W, padx=10, pady=10)

    # Value placeholders
    band_value = ttk.Label(root, text="Unknown", font=("Arial", 12))
    band_value.grid(row=0, column=1, sticky=tk.W, padx=10)

    freq_value = ttk.Label(root, text="Unknown", font=("Arial", 12))
    freq_value.grid(row=1, column=1, sticky=tk.W, padx=10)

    switch_value = ttk.Label(root, text="Unknown", font=("Arial", 12))
    switch_value.grid(row=2, column=1, sticky=tk.W, padx=10)

    tuner_value = ttk.Label(root, text="Unknown", font=("Arial", 12))
    tuner_value.grid(row=3, column=1, sticky=tk.W, padx=10)

    return root, band_value, freq_value, switch_value, tuner_value

def update_window(band_label, freq_label, switch_label, tuner_label, root):
    """Updates the Tkinter GUI with the latest data."""
    global bandName, freqDisplay, switch_position, tuner_setting

    # Update label text
    band_label.config(text=bandName)
    freq_label.config(text=freqDisplay)
    switch_label.config(text=switch_position)
    tuner_label.config(text=tuner_setting)

    # Schedule the next update
    root.after(1000, update_window, band_label, freq_label, switch_label, tuner_label, root)


# Match the K3 string to the desired band from the LUT
def get_JFP_band_select(bandval):
    global bandName
    
    for item in band_LUT:
        if item[5] == int(bandval):
            bandName = item[4]
            return item[1]  # Returning the 4th element as a string
    return "String not found in the table"

# Match the KAT500 string to a tune-request per the LUT
def get_tune_request(bandval):
    global bandName
    global tunerConfig
    global tuningTime
    global tuner_setting
    
    bandName = b''
    for item in band_LUT:
        if item[5] == int(bandval):
            tunerConfig = item[3]
            bandName = item[4]
            tuningTime = item[2]
    print(tunerConfig,"--",bandName)
    tuner_setting = tunerConfig
    
    if(bandName != b''):
        KAT500ser.write(tunerConfig) # set desired configuration on KAT500
        return tuningTime  # Returning the tuning time
            
    # Return None if the string is not found
    return None

# set the KAT500 antenna position
def setKat500(selnum):
    if(selnum == 1):
        KAT500ser.write(b'AN1;')
    if(selnum == 2):
        KAT500ser.write(b'AN2;')
    if(selnum == 3):
        KAT500ser.write(b'AN3;')

# Apply low-power TUNE signal to allow antenna tuners to adjust
def tune_default(secs):  
    if (MY_AUTOTUNE_ENABLE == "Y"):
        print("Tuning...")
        time.sleep(1)
        K3ser.write(b"SWH16;")  #LONG PRESS
        time.sleep(secs)            
        K3ser.write(b"SWT16;")  #SHORT PRESS
        time.sleep(0.2)
        print("Complete")
    else:
        print("Tuning Skipped")

##import telnetlib
##
##def open_telnet_connection(host, port, timeout=10):
##    try:
##        # Open a Telnet connection
##        print(f"Connecting to {host}:{port}")
##        tn = telnetlib.Telnet(host, port, timeout)
##        print(f"Connected to {host}:{port}")
##        return tn
##    except Exception as e:
##        print(f"Failed to connect to {host}:{port}: {e}")
##        return None
##
##def close_telnet_connection(tn):
##    try:
##        print("Closing connection.")
##        tn.close()
##        print("Connection closed.")
##    except Exception as e:
##        print(f"Error closing connection: {e}")
##        
### Apply low-power TUNE signal to allow antenna tuners to adjust
##def tune_default(secs):
##    global TuneTimer
##    
##    if MY_AUTOTUNE_ENABLE == "Y":
##        print("Tuning...")
##        TuneTimer = secs    ## picked up by async..
##
##        if TuneTimer > 0:
##            try:
##                tn = open_telnet_connection(MY_N3FJP_HOST, MY_N3FJP_PORT) 
##                cmd = "<CMD><SENDRIGCOMMAND><VALUE>SWH16;</VALUE></CMD>\n"
##                tn.write(cmd.encode())
##                response = tn.read_very_eager().decode('ascii')  # Read all available response data
##                print(f"Response1: {response}")                
##                print(f"waiting...{TuneTimer} seconds")
##                time.sleep(TuneTimer)
##                cmd = "<CMD><SENDRIGCOMMAND><VALUE>SWT16;</VALUE></CMD>\n"
##                tn.write(cmd.encode())
##                response = tn.read_very_eager().decode('ascii')  # Read all available response data
##                print(f"Response2: {response}")
##                time.sleep(1)
##                print("Complete")
##                TuneTimer = 0  # Reset tune_timer to 0
##                close_telnet_connection(tn)
##                                                    
##            except Exception as e:
##                print("An set_RIG error occurred:", e)
##
##    else:
##        print("Tuning Skipped")
        
### Set the WR9R Wifi-Enabled-Switch using HTTP_GET
MAX_RETRIES = 3
RETRY_DELAY = 2  # Delay in seconds between retries (optional)

def setWR9Rswitch(reply, data):
    global url
    global switch_position

    if reply is None:
        print("No Change")  # Handle case where reply is None
        return

    attempts = 0
    success = False
    switch_position = reply
    
    while attempts < MAX_RETRIES and not success:
        try:
            print(f"Attempt {attempts + 1}: Sending request to {url + reply}")
            response = requests.get(url + reply)

            if response.status_code == 200:
                print("Success!")
                success = True  # Mark success to exit retry loop

                if data != 0:
                    # Issue a 'Tune' to set auto-antenna tuning
                    tuningTime = get_tune_request(data)  # Get desired settings
                    print("Tune time =", tuningTime, "secs")
                    if MY_AUTOTUNE_ENABLE == "Y" and tuningTime != 0:
                        tune_default(tuningTime)
            elif response.status_code == 404:
                print("Web-Switch not found!")
                break  # No point retrying if resource doesn't exist
            else:
                print("Error:", response.status_code)
        except requests.RequestException as e:
            print(f"Request failed: {e}")
        finally:
            attempts += 1
            if not success and attempts < MAX_RETRIES:
                print("Retrying...")
                time.sleep(RETRY_DELAY)  # Wait before retrying

    if not success:
        print("Failed to set WR9R switch after 3 attempts.")


def setWR9R(data):
    reply = get_JFP_band_select(data)
    setWR9Rswitch(reply, data)                    

async def get_frequency(reader):
    global freqDisplay
    
    try:
        while True:
            # Read data from the connection
            data = await reader.readuntil(b'</FREQ>')
            # Convert bytes to string
            data_str = data.decode()      
            # Extract frequency value
            freq_match = re.search(r'<FREQ>(.*?)</FREQ>', data_str)
            if freq_match:
                freq = freq_match.group(1)
                print("Frequency:", freq)
                freqDisplay = freq
            else:
                break
    except Exception as e:
        print("An get_frequency error occurred:", e)

        
async def get_band(reader):
    global last_data
    global bandName
    global band
    global last_band
    global freq
    global last_freq
 
    try:
        while True:
            # Read data from the connection
            data = await reader.readuntil(b'</BAND>')
            # Convert bytes to string
            data_str = data.decode()

            # Extract band value
            band_match = re.search(r'<BAND>(.*?)</BAND>', data_str)
            if band_match:
                band = band_match.group(1)
                print("Band:", band)

                if ((band != None) and (band != last_band)):
                    setWR9R(band)
                    print("bn:" + bandName)
                    last_freq = freq
                    last_band = band
            else:
                break
                             
    except Exception as e:
        print("An get_band error occurred:", e)
        
##async def initialize_telnet_connection(host, port):
async def initialize_telnet_connection(host, port):
    try:
        reader, writer = await asyncio.open_connection(host, port)
        print(f"Connected to Telnet server at {host}:{port}")
        initial_commands = "<CMD><READ><CONTROL>TXTENTRYFREQUENCY</CONTROL></CMD>\n<CMD><READRESPONSE><CONTROL>TXTENTRYFREQUENCY</CONTROL></CMD>\n"
        writer.write(initial_commands.encode())
        return reader, writer
    
    except Exception as e:
        print(f"Failed to connect to Telnet server at {host}:{port}: {e}")
        return None, None

## Connect telnet and setup up background threads to gather data from N3JFP
async def Mymain():
    while True:
        host = MY_N3FJP_HOST
        port = MY_N3FJP_PORT
        
        reader_freq, writer_freq = await initialize_telnet_connection(host, port)
        reader_band, writer_band = await initialize_telnet_connection(host, port)
        
        if reader_freq and writer_freq and reader_band and writer_band:
            try:
                task1 = asyncio.create_task(get_frequency(reader_freq))
                task2 = asyncio.create_task(get_band(reader_band))
                await asyncio.gather(task1, task2)
                
            except Exception as e:
                print(f"Error in Telnet tasks: {e}")
                
            finally:
                if writer_freq:
                    writer_freq.close()
                    await writer_freq.wait_closed()
                if writer_band:
                    writer_band.close()
                    await writer_band.wait_closed()

                else:
                    print("Retrying connection in 5 seconds...")
                    
            await asyncio.sleep(5)

def start_async_loop():
    asyncio.run(Mymain())

## Initialize serial ports, open the window, start the threads to service connections and
## update the window values
def WR9R_init():
    global KAT500ser
    global K3ser
    
    print("WR9R Elecraft N3FJP Antenna Manager", MY_VERSION)

    # Send initial commands
    if (MY_AUTOTUNE_ENABLE == "Y"):
        K3ser = serial.Serial(MY_K3_COMM_PORT, baudrate=MY_COMM_RATE)  # K3 Connect
        K3ser.rts = False
        K3ser.dtr = False

    KAT500ser = serial.Serial(MY_KAT500_COMM_PORT, baudrate=MY_COMM_RATE)  # KAT500 Connect
    KAT500ser.write(b'AN1;MDM;')  # Starting KAT500 state

    # Setup GUI
    root, band_label, freq_label, switch_label, tuner_label = draw_window()

    # Start asyncio tasks in a thread
    async_thread = threading.Thread(target=start_async_loop, daemon=True)
    async_thread.start()

    # Start GUI update loop
    update_window(band_label, freq_label, switch_label, tuner_label, root)

    # Run the Tkinter event loop
    root.mainloop()   

## on Window Close -- shut down ports and exit the script
def WR9R_shutdown():
    if (MY_AUTOTUNE_ENABLE == "Y"):
        K3ser.close()

    KAT500ser.close()
    exit()

if __name__ == "__main__":
    WR9R_init()
