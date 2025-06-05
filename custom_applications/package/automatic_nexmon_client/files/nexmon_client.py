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
SHMEM_BASE_ADDR = 0x09000000            # Base address of crosscon shared memory region
SHMEM_SIZE = 0x00800000                 # Size of crosscon shared memory (in bytes I think)
# We have to set it to 0x00800000 (5 zeroes) for around 8MiB of shared memory

PARAM_ADDR = 0                          # Which byte starting at SHMEM_BASE_ADDR contains the flag bits
PARAM_BYTE_SIZE = 312                   # As defined per our API
PARAM_WITHOUT_MAC_SIZE = 12             # This is how many first bytes of param memory are used for classical parameters without the actual macs

# --- nexmon_csi and protocol specific configuration values ---
MAX_DEVICES = 50                        # If this were to be more, the area for params would need to be bigger as well
RAW_CSI_DATA_SIZE = 256
FULL_SAMPLE_SIZE = RAW_CSI_DATA_SIZE + 2 + 2 + 1 + 6        # 256 (CSI) + 2 (StreamId) + 2 (TimeOffset) + 1 (RSSI) + 6 (MAC)
CSI_HEADER_LEN = 18                                     # hence this is also the offset at which one has to index start to get the CSI data, given a UDP packet

DATA_ADDR = PARAM_ADDR + PARAM_BYTE_SIZE                # At which byte does the data start. In respect to SHMEM_BASE_ADDR and PARAM_BYTE_SIZE (default is 312 because PARAM_SIZE is 312)
DATA_MEMORY_MAX_SIZE = SHMEM_SIZE - PARAM_BYTE_SIZE      # around 4,2MiB (should be 22 for that)
DATA_MAX_SAMPLES = DATA_MEMORY_MAX_SIZE // FULL_SAMPLE_SIZE
# how many data entries will be written is defined by other params

# eduroam mac: e8:10:98:d1:8b:a0  6/20
# 0x0000001E64140600        # this is 6/20, 100 samples_p_d, 30 sekunden, no filter
# 0x0000001E00140600        # this is 6/20, 0 samples_p_d, 30 sekunden, no filter

# 0x0001001E64140681        # this is 6/20, 100 samples_p_d, 30 sekunden, 1 device, with filter and elements in filter folloiwing:
# 0xd19810e800000000        # this is at 0x8000008 64
# 0x000000000000a08b        # this is at 0x8000010 64

# --- Definition of return values ---
#
# - 0:      Never hit
# - 1:      Failed, due to number_of_macs specified exceeding MAX_DEVICES
# - 2:      Failed, due to combination of samples_per_device and number_of_macs exceeding DATA_MEMORY_MAX_SIZE      (only valid if mac filter is on)
# - 3:      Failed, due to a failing subprocess during nexmon configuration
# - 4:      Failed, due to a generic exception during nexmon configuration
# - 5:      Failed, due to a generic exception during main loop
# - 6:      Succeeded, with Active MAC filter due to all samples collected
# - 7:      Succeeded, due to timeout
# - 8:      Succeeded, with INActive MAC filter due to DATA_MAX_SAMPLES hit
# - 9:      Failed, due to unforseen reason during data gathering
# - 10:     Failed, due to failed aligned writing to devmem
# - 11:     Never hit. Used to indicate starting bit NOT set
# - 12:     Failed, due to failed aligned reading from devmem

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
                ("time_offset", c_uint16),
                ("data", c_uint8 * RAW_CSI_DATA_SIZE)
        ]
        
assert sizeof(Data_Entry) == FULL_SAMPLE_SIZE, "Mismatch in Data_Entry size!"

# --- Open /dev/mem ---
# file descriptor to /dev/mem with ReadWrite capabilites operating in synchronous mode (direct flushes)
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)


# --- Helper to get read and write from and to devmem in a page aligned matter accessing one page at a time
def write_to_devmem_aligned(base_addr, data_bytes, length) -> int:
        """
        We always have to write a full page. Therefore, you must assure yourself that you don't overwrite previous stuff
        """
        try:
                offset = 0        
                while offset < length:
                        page_start = (base_addr + offset) & PAGE_MASK
                        page_offset = (base_addr + offset) - page_start
                        chunk_size = min(PAGE_SIZE - page_offset, length - offset)
                        
                        # next line gets the correct memory region using:
                                # MAP_SHARED (for shared changes to memory between processes)
                                # PROT_WRITE (for writing capabilites)
                                # PROT_READ (for reading capabilites)
                        mem = mmap.mmap(fd, PAGE_SIZE, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=page_start)
                        mem.seek(page_offset)
                        
                        chunk = data_bytes[offset : offset + chunk_size]
                        
                        if page_offset + chunk_size < PAGE_SIZE:
                                padding_len = PAGE_SIZE - (page_offset + chunk_size)
                                chunk += b'\x00' * padding_len
                                
                        mem.write(chunk)
                        mem.close()
                        
                        offset += chunk_size
                return 0
        except Exception as e:
                print(f"During aligned writing to memory at byte offset: {offset} this error occurred. Returning with 10\n: {e}")
                return 10

def read_from_devmem_aligned(base_addr, length) -> bytearray | None:
        """
        We always read an entire Page otherwise we might get a Bus Error
        """
        try:
                result = bytearray(length)
                offset = 0
                
                while offset < length:
                        page_start = (base_addr + offset) & PAGE_MASK
                        page_offset = (base_addr + offset) - page_start
                        chunk_size = min(PAGE_SIZE - page_offset, length - offset)
                        
                        # next line gets the correct memory region using:
                                # MAP_SHARED (for shared changes to memory between processes)
                                # PROT_READ (for reading capabilites)
                        mem = mmap.mmap(fd, PAGE_SIZE, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ, offset=page_start)
                        
                        page_data = mem.read(PAGE_SIZE)
                        result[offset : offset + chunk_size] = page_data[page_offset : page_offset + chunk_size]
                        mem.close()
                        
                        offset += chunk_size
                        
                return result
        except Exception as e:
                print(f"During algined reading of memory at byte offset: {offset} this error occurred. Returning None\n: {e}")
                return None


# --- Helpers to retrieve and write Parameters object
def get_params_object() -> Parameters | None:
        """ Get a Parameters object from shared memory region or None if its start bit is not set. """
        raw = read_from_devmem_aligned(SHMEM_BASE_ADDR + PARAM_ADDR, PARAM_BYTE_SIZE)
        
        # check if read succeded
        if raw is None:
                return None
        else:
            return Parameters.from_buffer(raw)


def write_params(params, ret_val):
        """ Write Parameters object to shared memory. Internally it sets finish and ret_val before though."""
        if params == None:
            params = Parameters(
                    flags=0b10,
                    channel=0,
                    bandwidth=0,
                    samples_per_device=0,
                    timeout=0,
                    number_of_macs=0,
                    return_val=0,
                    number_retrieved_total_samples=0,
                    macs=(c_uint8 * (PARAM_BYTE_SIZE - PARAM_WITHOUT_MAC_SIZE))()
            )
        params.return_val = ret_val
        params.flags &= ~0b11       # clear start bit
        params.flags |= 0b10        # set finish bit
        
        raw = string_at(addressof(params), sizeof(params))
        write_to_devmem_aligned(SHMEM_BASE_ADDR + PARAM_ADDR, raw, PARAM_BYTE_SIZE)


# --- Helper to toggle the rpi on board LED to illustrate nexmon_client working
def set_led(brightness_value):
        try:
                with open("/sys/class/leds/ACT/brightness", "w") as led_brightness:
                        led_brightness.write(str(brightness_value))
        except Exception as e:
                print(f"Could not access on board LED due to: {e}")


# --- Helper to configure nexmon ---
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
                print("Error:", e.stderr.decode() if e.stderr else "")
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

        samples_per_device = params.samples_per_device if params.samples_per_device != 0 else DATA_MAX_SAMPLES
        number_of_macs = params.number_of_macs
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
        
        offset_start = time.perf_counter()

        try:
                while datetime.now() < end_time:
                        try:    
                                # start listening for UDP packets
                                data, _  = sock.recvfrom(MAX_BUFFER_SIZE)
                                if len(data) < HEADER_LEN:
                                        continue
                                        
                                # mark the time point where a packet has been retrieved
                                offset_end = time.perf_counter()

                                # get rssi (and magic value)
                                magic, rssi = struct.unpack('<HB', data[:3])
                                if magic != 0x1111:     # check magic value
                                        print("magic value not matching")
                                        continue

                                # get mac and check for filter
                                src_mac_bytes = data[4:10]
                                mac_str = ':'.join(f'{b:02x}' for b in src_mac_bytes)

                                if mac_filtering_enabled and mac_str not in mac_whitelist:
                                        continue

                                # get stream_id
                                stream_id = struct.unpack('<H', data[12:14])[0]

                                # get csi data
                                csi_start = HEADER_LEN
                                csi_data = data[csi_start:csi_start+RAW_CSI_DATA_SIZE]
                                if len(csi_data) < RAW_CSI_DATA_SIZE:
                                        print(f"csi data was smaller than {RAW_CSI_DATA_SIZE} : ${len(csi_data)}")
                                        continue

                                mac_parts = struct.unpack('6B', src_mac_bytes)
                                time_offset = min(int(offset_end - offset_start), 0xFFFF)           # this is to prevent uint16 overflowing
                                entry = Data_Entry(
                                        rssi=rssi,
                                        mac=(c_uint8 * 6)(*mac_parts),
                                        stream_id=stream_id,
                                        time_offset=time_offset,
                                        data=(c_uint8 * RAW_CSI_DATA_SIZE).from_buffer_copy(csi_data)
                                )

                                if mac_str not in collected_data:
                                        collected_data[mac_str] = []

                                if len(collected_data[mac_str]) < samples_per_device:
                                        collected_data[mac_str].append(entry)


                                # check if number of already fetched samples exceeds max amount of samples
                                if sum(len(v) for v in collected_data.values()) >= DATA_MAX_SAMPLES:
                                        ret_code = 8
                                        break
                                        
                                # check if all devices have fetched enough samples (when mac filter is active)
                                if mac_filtering_enabled and all(len(v) >= samples_per_device for v in collected_data.values()):
                                        ret_code = 6
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
        params.number_retrieved_total_samples = min(len(all_entries), 0xFFFFFFFF)           # this mask is to prevent uint32 overflowing

        return params, entries_bytes, len(entries_bytes), ret_code



def check_params_object(parameters) -> int:
        """ 
        We have four different status codes:
        - 0: all fine
        - 1: too many devices
        - 2: combination of samples_per_device and number_of_macs exceeds DATA_MEMORY_MAX_SIZE
        - 11: start bit is not set
        """
        if not (parameters.flags & 0b1):
                # 11 is status code for start bit not set
                return 11

        if  parameters.number_of_macs > MAX_DEVICES:
                # 1 is status code for too many devices (greater than 50)
                return 1
        if (parameters.samples_per_device != 0) and (parameters.samples_per_device * parameters.number_of_macs * FULL_SAMPLE_SIZE > DATA_MEMORY_MAX_SIZE):
                # 2 is status code for combination of samples_per_device and number of devices exceeds memory space
                return 2

        # parameters struct looks fine
        return 0



# --- Actual execution loop ---
def main():
        print("Nexmon client started. Monitoring memory.")

        while True:
                try:
                        # try to get Parameters object
                        params = get_params_object()
                        if params is None:
                                # 12 is status code for reading of parameters failed
                                write_params(params, 12)
                                continue

                        # check whether parameters are within memory bounds
                        check_ret = check_params_object(params)
                        if check_ret != 0:
                                if check_ret == 11:
                                        # wait one second before trying again
                                        time.sleep(1)
                                        continue
                                else:
                                        # parameters object is not fine, therefore report an error
                                        write_params(params, check_ret)
                                        continue
                                        
                        #print("Starting bit was set")
                        print(f"Parameters: {params}")

                        # now configure nexmon
                        check_ret = configure_nexmon(params.channel, params.bandwidth)
                        if check_ret != 0:
                                # configuration of nexmon failed, therefore report the error
                                write_params(params, check_ret)
                                continue

                        # Start nexmon_csi data fetching
                        set_led(250)

                        params, raw_data_bytes, total_bytes, check_ret = get_data_nexmon(params)
                        print(f"total samples:{params.number_retrieved_total_samples}")
                        if (not ( 6 <= check_ret <= 8) ):
                                # status code 9: somewhere during the fetching of data via nexmon an error occurred
                                write_params(params, 9)
                                continue
                                

                        # write data and finished params to memory
                        # finish params
                        params.return_val = check_ret   # set return val
                        params.flags &= ~0b11       # clear start bit
                        params.flags |= 0b10        # set finish bit
                        
                        # prepend raw_data_bytes with params
                        raw_data_bytes = string_at(addressof(params), sizeof(params)) + raw_data_bytes
                        
                        # write to memory
                        check_ret = write_to_devmem_aligned(SHMEM_BASE_ADDR + PARAM_ADDR, raw_data_bytes, len(raw_data_bytes))
                        if check_ret != 0:
                                # writing samples to memory failed, therefore report the error
                                write_params(params, check_ret)
                                continue

                        # toggle back led
                        set_led(0)
                        print("Finished Query")

                        # sleep for one seconds before restarting
                        time.sleep(1)

                except Exception as e:
                        print("An error in nexmon client occurred: ", e)
                        # write status code 5 for error during running loop
                        write_params(None, 5)

if __name__ == "__main__":
        main()
