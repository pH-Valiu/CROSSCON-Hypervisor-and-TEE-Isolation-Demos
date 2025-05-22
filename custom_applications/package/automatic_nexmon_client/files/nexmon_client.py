import mmap
import struct
import os
import time
import subprocess
import socket
from ctypes import Structure, c_uint8, c_uint16, c_uint32, sizeof, addressof, string_at
from datetime import datetime, timedelta

# needed for page alignment, we always have to access memory a page starts
PAGE_SIZE = mmap.PAGESIZE       # e.g. 4096 (0x00001000)
PAGE_MASK = ~(PAGE_SIZE -1)     # e.g. as 4096 - 1= 4095 (0x00000FFF) -> ~4095 = 0xFFFFF000

# --- Configuration ---
SHMEM_BASE_ADDR = 0x08000000            # Base address of crosscon shared memory region
SHMEM_SIZE = 0x00200000                 # Size of crosscon shared memory (in bytes I think)
# We have to set it to 0x00800000 (5 zeroes) for around 8MiB of shared memory

PARAM_ADDR = 0                          # Which byte starting at SHMEM_BASE_ADDR contains the flag bits
PARAM_BYTE_SIZE = 312                   # As defined per our API
PARAM_WITHOUT_MAC_SIZE = 12             # This is how many first bytes of param memory are used for classical parameters without the actual macs

# --- nexmon_csi and protocol specific configuration values ---
MAX_DEVICES = 50                        # If this were to be more, the area for params would need to be bigger as well
RAW_CSI_DATA_SIZE = 255
FULL_SAMPLE_SIZE = RAW_CSI_DATA_SIZE + 2 + 1 + 6
CSI_HEADER_LEN = 19

DATA_ADDR = PARAM_ADDR + PARAM_BYTE_SIZE    # At which byte does the data start. In respect to SHMEM_BASE_ADDR and PARAM_BYTE_SIZE (default is 312 because PARAM_SIZE is 312)
DATA_MEMORY_MAX_SIZE = 1 << 20              # around 4,2MiB (should be 22 for that)
DATA_MAX_SAMPLES = DATA_MEMORY_MAX_SIZE // FULL_SAMPLE_SIZE
# how many data entries will be written is defined by other params

# 0x010B14040020

# --- Parameter Object Structure ---
class Parameters(Structure):
        _pack_ = 1
        _fields_ = [
                ("flags", c_uint8),
                ("channel", c_uint8),
                ("bandwidth", c_uint8),
                ("samples_per_device", c_uint8),
                ("timeout", c_uint16),
                ("number_of_macs", c_uint8),
                ("return_val", c_uint8),
                ("number_retrieved_total_samples", c_uint32),
                ("macs", c_uint8 * (PARAM_BYTE_SIZE - PARAM_WITHOUT_MAC_SIZE))
        ]
        
        def get_mac_list(self):
                """ Return list of mac addresses as strings"""
                return [
                        ':'.join(f'{b:02x}' for b in self.macs[i*6:i*6+6])
                        for i in range(self.number_of_macs)
                ]
                
        def __str__(self):
                mac_list = self.get_mac_list()
                macs_formatted = '\n  '.join(mac_list) if mac_list else 'None'
                return (
                        f"Parameters:\n"
                        f"  Flags: 0b{self.flags:08b} ({self.flags})\n"
                        f"  Channel: {self.channel}\n"
                        f"  Bandwidth: {self.bandwidth}\n"
                        f"  Samples per Device: {self.samples_per_device}\n"
                        f"  Timeout: {self.timeout} seconds\n"
                        f"  Number of MACs: {self.number_of_macs}\n"
                        f"  Return Value: {self.return_val}\n"
                        f"  Retrieved Samples: {self.number_retrieved_total_samples}\n"
                        f"  MAC List:\n  {macs_formatted}"
                )
                
                
# --- Data Entry Object Structure ---
class Data_Entry(Structure):
        _pack_ = 1
        _fields_ = [
                ("rssi", c_uint8),
                ("mac", c_uint8 * 6),
                ("stream_id", c_uint16),
                ("data", c_uint8 * RAW_CSI_DATA_SIZE)
        ]


# --- Open /dev/mem ---
# file descriptor to /dev/mem with ReadWrite capabilites operating in synchronous mode (direct flushes)
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)


# --- Helper to get mmap and correct offset for destined physical address area
def mmap_phys(phys_addr, length):
        page_base = phys_addr & PAGE_MASK
        page_offset = phys_addr - page_base

        # next line gets the correct memory region using:
                # MAP_SHARED (for shared changes to memory between processes)
                # PROT_WRITE (for writing capabilites)
                # PROT_READ (for reading capabilites)
        mem = mmap.mmap(fd, length + page_offset, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=page_base)

        # return memory region plus the offset at where to start accessing it
        return mem, page_offset


# --- Helper to toggle the rpi on board LED to illustrate nexmon_client working
def set_led(brightness_value):
        with open("/sys/class/leds/ACT/brightness", "w") as led_brightness:
                led_brightness.write(str(brightness_value))

def configure_nexmon(channel, bandwidth):
        try:
                # Step 1: Run makecsiparams and capture output
                csiparams = makecsiparams(channel, bandwidth)
                print(f"makecsiparams output: {csiparams}")

                # Step 1.5: Bring wifi interface up
                subprocess.run(["ifconfig", "wlan0", "up"], check=True)
                print("Wifi interface 'wlan0' is up.")

                # Step 2: Run nexutil with captured output
                nexutil(csiparams)
                print("nexutil configured.")

                # Step 3.1 Check if mon0 already exists, and delete it if so
                result = subprocess.run(["ip", "link", "show", "mon0"], capture_output=True, text=True)
                if result.returncode == 0:
                        print("mon0 already exists. deleting it now")
                        subprocess.run(["iw", "dev", "mon0", "del"], check=True)

                # Step 3.2: Create monitor interface
                subprocess.run(
                        ["iw", "phy", "phy0", "interface", "add", "mon0", "type", "monitor"],
                        check=True
                )
                print("Monitor interface 'mon0' created.")

                # Step 4: Bring interface up
                subprocess.run(["ifconfig", "mon0", "up"], check=True)
                print("Monitor interface 'mon0' is up.")

                return 0

        except subprocess.CalledProcessError as e:
                print("Command failed:", e.cmd)
                print("Return code:", e.returncode)
                print("Output:", e.output if e.output else "")
                print("Error:", e.stderr if e.stderr else "")
                # 3 status code indicates an error during a subprocess routine of nexmon configuration
                return 3
        except Exception as e:
                print("Unexpected error:", e)
                # 4 status code indicates a general exception during nexmon configuration
                return 4

def makecsiparams(channel, bandwidth):
        result = subprocess.run(["makecsiparams", "-c", f"{channel}/{bandwidth}", "-C", "1", "-N", "1"], capture_output=True, check=True, text=True)
        return result.stdout.strip()

def nexutil(csiparams):
        subprocess.run(["nexutil", "-Iwlan0", "-s500", "-b", "-l34", f"-v{csiparams}"], capture_output=True, check=True)

def get_data_nexmon(params):
        print("Called get_data_nexmon")
        UDP_PORT = 5500
        MAX_BUFFER_SIZE = 4069
        HEADER_LEN = CSI_HEADER_LEN
        
        samples_per_device = params.samples_per_device
        mac_filtering_enabled = bool(params.flags & 0b10000000)
        
        if mac_filtering_enabled:
                mac_whitelist = set(params.get_mac_list())
                collected_data = {mac: [] for mac in mac_whitelist}
        else:
                mac_whitelist = None
                collected_data = {}

        end_time = datetime.now() + timedelta(seconds=params.timeout)
        

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', UDP_PORT))
        sock.settimeout(1.0)
        
        try:
                while datetime.now() < end_time:
                        try:
                                data, _  = sock.recvfrom(MAX_BUFFER_SIZE)
                                if len(data) < HEADER_LEN:
                                        continue
                                
                                # get rssi (and magic value)
                                magic, rssi = struct.unpack('<HB', data[:3])
                                if magic != 0x1111:     # check magic value
                                        print("magic value not matching")
                                        continue
                                        
                                # get mac and check for filter
                                src_mac_bytes = data[5:11]
                                mac_str = ':'.join(f'{b:02x}' for b in src_mac_bytes)
                                
                                if mac_filtering_enabled and mac_str not in mac_whitelist:
                                        print("sample mac was not in filter")
                                        continue
                                
                                # get stream_id
                                stream_id = struct.unpack('<H', data[13:15])[0]
                                
                                # get csi data
                                csi_start = HEADER_LEN
                                csi_data = data[csi_start:csi_start+RAW_CSI_DATA_SIZE]
                                if len(csi_data) < RAW_CSI_DATA_SIZE:
                                        print(f"csi data was smaller than {RAW_CSI_DATA_SIZE} : ${len(csi_data)}")
                                        continue
                                        
                                mac_parts = struct.unpack('6B', src_mac_bytes)
                                entry = Data_Entry(
                                        rssi=rssi,
                                        mac=(c_uint8 * 6)(*mac_parts),
                                        stream_id=stream_id,
                                        data=(c_uint8 * RAW_CSI_DATA_SIZE).from_buffer_copy(csi_data)
                                )
                                
                                if mac_str not in collected_data:
                                        collected_data[mac_str] = []
                                
                                if len(collected_data[mac_str]) < samples_per_device:
                                        collected_data[mac_str].append(entry)
                                        
                                
                                if mac_filtering_enabled:
                                        # check if all devices have fetched enough samples
                                        if all(len(v) >= samples_per_device for v in collected_data.values()):
                                                ret_code = 6
                                                break
                                else:
                                        # check if number of already fetched samples surpases max amount of samples
                                        if sum(len(v) for v in collected_data.values()) >= DATA_MAX_SAMPLES:
                                                ret_code = 8
                                                break
                                        
                        except socket.timeout:
                                continue
                                
                else:
                        ret_code = 7
                        
        finally:
                sock.close()
                
                
        
        # flatten the entries
        all_entries = []
        for entries in collected_data.values():
                all_entries.extend(entries[:samples_per_device])
                
        entries_bytes = b''.join(string_at(addressof(entry), sizeof(entry)) for entry in all_entries)
        
        # update params object
        params.number_retrieved_total_samples = len(all_entries)
        
        return params, entries_bytes, len(entries_bytes), ret_code

def get_params_object(param_mem, param_offset):
        """ Get a Parameters object from shared memory region or None if its start bit is not set. """
        param_mem.seek(param_offset)
        raw_bytes = param_mem.read(PARAM_BYTE_SIZE)
        
        # directly parse the memory into a C like struct
        parameters = Parameters.from_buffer_copy(raw_bytes)
        print(parameters.__str__())
        
        if parameters.flags & 0b1:
                # start bit is set: return parameters object
                return parameters
        else:
                # start bit is not set
                return None
    
def check_params_object(parameters):
        if  parameters.number_of_macs > MAX_DEVICES:
                # 1 is status code for too many devices (greater than 50)
                return 1
        if (parameters.samples_per_device * parameters.number_of_macs * FULL_SAMPLE_SIZE > DATA_MEMORY_MAX_SIZE):
                # 2 is status code for combination of samples_per_device and number of devices exceeds memory space
                return 2
        
        # parameters struct looks fine
        return 0
        
def write_params(param_mem, param_offset, parameters, ret_val):
        parameters.return_val = ret_val
        parameters.flags ^= 0b11      # this sets start bit back to 0 and finish bit to 1

        # write params back to memory
        params_bytes = string_at(addressof(parameters), sizeof(parameters))
        param_mem.seek(param_offset)
        param_mem.write(params_bytes)

# --- Actual execution loop ---
def main():
        print("Nexmon client started. Monitoring memory.")

        # Get memory region of parameters
        param_mem, param_offset = mmap_phys(SHMEM_BASE_ADDR + PARAM_ADDR, PARAM_BYTE_SIZE)
        while True:
                try:
                        # try to get Parameters object
                        params = get_params_object(param_mem, param_offset)
                        if params == None:
                                # wait one second before trying again
                                time.sleep(1)
                                continue
                        
                        print("Starting bit was set")
                        
                        # check whether parameters are within memory bounds
                        check_ret = check_params_object(params)
                        if check_ret != 0:
                                # parameters object is not fine, therefore report an error
                                write_params(param_mem, param_offset, params, check_ret)
                                continue
                                

                        # now configure nexmon
                        check_ret = configure_nexmon(params.channel, params.bandwidth)
                        if check_ret != 0:
                                # configuration of nexmon failed, therefore report the error
                                write_params(param_mem, param_offset, params, check_ret)
                                continue

                        # Start nexmon_csi data fetching
                        set_led(250)

                        params, raw_data_bytes, total_bytes, check_ret = get_data_nexmon(params)
                        print(f"total samples:{params.number_retrieved_total_samples}")
                        if (not ( 6 <= check_ret <= 8) ):
                                # status code 9: somewhere during the fetching of data via nexmon an error occurred
                                write_params(param_mem, param_offset, params, 9)
                                continue

                        # write data to memory
                        data_mem, data_mem_offset = mmap_phys(SHMEM_BASE_ADDR + DATA_ADDR, total_bytes)
                        data_mem.seek(data_mem_offset)
                        data_mem.write(raw_data_bytes)
                        data_mem.close()
                        
                        # write finished params to memory
                        # set finish flags
                        write_params(param_mem, param_offset, params, check_ret)
                      
                        # toggle back led
                        set_led(0)

                        # sleep for one seconds before restarting
                        time.sleep(1)
                        
                except Exception as e:
                        print("An error in nexmon client occurred: ", e)
                        # write status code 5 for error during running loop
                        write_params(param_mem, param_offset, params, 5)

if __name__ == "__main__":
        main()
