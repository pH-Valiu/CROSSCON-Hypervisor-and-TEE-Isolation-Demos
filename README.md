# Complete Guide - Building a Linux VM containing NEXMON_CSI and shared memory protocol running on CROSSCON Hypervisor

This guide completely describes the process of building a working Linux VM containing the nexmon_csi package as well as automated startup scripts.
Further, this Linux VM is directly integrated in the CROSSCON Hypervisor.
We will show, the required configuration steps, the building process and how to manually test nexmon csi or control it over a shared memory protocol.

Side notes:
- If you just need the VM, that is possible too. Please follow the guide though first and then see this chapter [Using just the Linux VM](#using-just-the-linux-vm).
- This guide is the culmination of all my complete work and many different singular `.md` guides that focused on a single point of the full process. In case of errors in this guide, you might wanna check out the others as well.
<details>
    <summary><b>Other interesting Guides:</b></summary>
	
- Setting up the docker environment for building: [env/README.md](env/README.md)
- Most simplest Linux VM on RPI4: [rpi4-ws/README.md](rpi4-ws/README.md) (following this guide in this branch might not lead to success)
- Adding custom packages in Linux VM build via Buildroot: [ADDING_CUSTOM_PACKAGES.md](ADDING_CUSTOM_PACKAGES.md)
- Enabling wifi in Linux VM running on CROSSCON Hypervisor: [BUILDROOT_WIFI_INTEGRATION.md](BUILDROOT_WIFI_INTEGRATION.md)
- Including nexmon_csi in Linux VM running on CROSSCON Hypervisor: [BUILDROOT_NEXMON_INTEGRATION.md](BUILDROOT_NEXMON_INTEGRATION.md)
</details>

## **Requirements**
- We compile for **aarch64 RPI4** and assume [rpi4.dts](rpi4-ws/rpi4.dts) to be its correct device tree!
- Please use the docker environment for building! A guide on how to setup that docker environment can be found here: [env/README.md](env/README.md).
- Linux Kernel needs to be compiled for version 5.10.92-v8+ inside Buildroot and not externally.
- We need to enable the WIFI chip in the Hypervisor config file using the RPI device tree. See [this section](#changes-in-crosscon-hypervisor-config-configc). 

Please refer to the [nexmon_automated_demo](nexmon_automated_demo) folder containing:
- all `.config` files for proper building of the VM
- the two [custom applications](nexmon_automated_demo/custom_applications) that have to be shipped onto the VM
- the `config.c` to build the CROSSCON Hypervisor with

## Structure
1. [Configurations](#configurations):
    1. [Adding custom applications](#adding-custom-applications)
    2. [Buildroot config](#changes-in-buildroot-config-br-aarch64config)
    3. [Linux config](#changes-in-buildroot-kernel-config-linux-aarch64config)
    4. [BusyBox config](#file-contents-of-busybox-additionalconfig)
    5. [CROSSCON Hypervisor config](#changes-in-crosscon-hypervisor-config-configc)
2. [Building](#building):
    1. [Setup firmware components](#step-1---setup-firmware-components)
    2. [Build OP-TEE OS](#step-2---building-the-op-tee-os)
    3. [Build kernel & filesystem](#step-3---invoke-buildroot)
    4. [Create CROSSCON Hypervisor](#step-7---build-crossconhypbin)
3. [Testing](#testing):
    1. [Manual nexmon csi software testing](#manual-nexmon-csi-testing)
    2. [Using the shared memory protocol to communicate with nexmon csi](#shared-memory-protocol-for-communication):
	1. [Protocol definition](#protocol-definition)
	2. [Protocol usage in production](#protocol-usage-in-production)
4. [Additional notes](#additional-notes):
    1. [Using just the Linux VM](#using-just-the-linux-vm)

## Configurations
As a quick note to start with:
In the following, we create three `.config` files that have to be moved to `/work/crosscon/buildroot/build-aarch64/`.
One `config.c` file that has to be moved to `/work/crosscon/rpi4-ws/configs/rpi4-single-vTEE/`.
A `custom_applications` folder that has to be moved to `/work/crosscon/`.

### Adding custom applications
Before we start configuring buildroot, we have to make sure that our two custom applications (*nexmon* and *automatic_nexmon_client*) are located in `/work/crosscon/custom_applications`.
For that, simply copy [nexmon_automated_demo/custom_applications](nexmon_automated_demo/custom_applications) folder into `/work/crosscon` via:
```sh
cp -r /work/crosscon/nexmon_automated_demo/custom_applications/ /work/crosscon/
```

A few informations about every package:
1. *nexmon*:
    - Contains `makecsiparams` binary to be found under `/usr/bin` in VM
    - Contains `nexutil` binary to be found under `/usr/bin` in VM
    - Contains `brcmfmac43455-sdio.bin` wifi firmware which replaces the original firmware in `lib/firmware/brcm/` in VM
    - Contains `brcmfmac.ko` wifi driver which replaces the original driver in `/lib/modules/5.10.92-v8+/kernel/drivers/net/wireless/broadcom/brcm80211/brcmfmac/brcmfmac.ko` in VM

    - These are precompiled binaries compiled for raspberrypi kernel version **5.10.92-v8+**. They are being automatically downloaded from [here](https://github.com/pH-Valiu/nexmon_csi_bin).
2. *automatic_nexmon_client*:
    - Contains `S90nexmon` startup script which inserts the nexmon_csi kernel module and launches our shared memory protocol via the python script in the VM. That file can be found in `/etc/init.d` in VM
    - Contains `nexmon_client.py` python script which handles the protocol. Can be found under `/usr/bin` in VM

    - These files are local and can be found in the `automatic_nexmon_client` package under the `files` folder.

To link this `custom_applications` folder to buildroot, whenever (or actually just the first time) invoking `make` commands in `/work/crosscon/buildroot`, add `BR2_EXTERNAL=/work/crosscon/custom_applications` as argument.

To understand, how you'd generally include custom packages into your filesystem via Buildroot, either refer to the official Buildroot documentation or see [this guide](ADDING_CUSTOM_PACKAGES.md)

### Changes in Buildroot config [`br-aarch64.config`](nexmon_automated_demo/br-aarch64.config)
First of: Move to `/work/crosscon/buildroot`. 
Now, we will checkout to an older version of buildroot for which we have made sure that our guide works.
```sh
git checkout 2022.11.x
```
Afterwards, invoke: 
```
mkdir build-aarch64
```

Now you have two options:
- Either copy [br-aarch64.config](nexmon_automated_demo/br-aarch64.config) directly into `/work/crosscon/buildroot/build-aarch64` as `.config`
- Or manually "create" the file using buildroots menuconfig and [this file](support/br-aarch64.config) as base.

Since the first approach is really straightforward, I will now focus on what the required changes to the base file (`support/br-aarch64.config`) are:

First, call:
```
make O=build-aarch64 BR2_EXTERNAL=/work/crosscon/custom_applications menuconfig
```
(We need to link to our external custom_applications tree as that folder will later contain the configuration files required to include nexmon_csi and the shared memory protocol in the buildroot build pipeline.<br>
As long as the future `build-aarch64/.config` is not deleted, we don't need to add `BR2_EXTERNAL=...` to future `make` calls invoked inside the Buildroot directory.)

Now a settings menu should appear. **Load** our base file: `/work/crosscon/support/br-aarch64.config`. Then, after you have all applied all changes, **Save** the changes in the same file. Now copy the file into `build-aarch64` using 
```sh
cp /work/crosscon/support/br-aarch64.config /work/crosscon/buildroot/build-aarch64/.config
```
Alternatively, you could also directly **Save** into `/work/crosscon/buildroot/build-aarch64/.config`.

<br>
Apply the following changes:

- **Target Architecture**:
    - Please make changes as required to fit your hardware. Following are the settings for the RPI:
    - Set **Target Architecture** to `AArch64 (little endian)`
    - Set **Target Architecture Variant** to `cortex-A53`
    - Set **Floating point strategy** to `FP-ARMv8`
    - Set **MMU Page Size** to `4KB`
    - Set **Target Binary Format** to `ELF`
- **Toolchain**:
    - Set the **Kernel Headers** field to the same kernel version (e.g. *5.10.x*) as you want your kernel build
    - We worked with **Binutils version** `binutils 2.38` but others might work as well
    - We worked with **GCC compiler Version** `gcc 11.x` but others might work as well
    - Enable `C++ Support` (needed for nexmon_csi)
- **System configuration**:
    - For **Init system**: Set `BusyBox`
    - For **/dev management**: Set `Dynamic using devtmpfs only`
    - For **Root Filesystem overlay directories**: Keep the paths to the export directories of your additional OP-TEE related binaries until you divert to including them the proper way using the Buildroot packaging system or outright excluding them because they are not really needed for the Nexmon Linux VM.
- **Kernel**:
    - Enable `Kernel`
    - For **Kernel Version**: Set it to `(Custom Git Repository)`
    - For **URL of custom repository**: Set it to `https://github.com/pH-Valiu/linux_raspberrypi.git` or any comparable repository like that.
    - For **Custom repository version**: Set it to `rpi-5.10.92-port` as it contains the code at kernel version 5.10.92 with 3 additional commit required for CROSSCON Hypervisor.
    - For **Kernel configuration**: Set it to `Using a custom (def)config file` and specify `/work/crosscon/buildroot/build-aarch64/linux.config` as your kernel config file
    - Checkmark `Build a Device Tree Blob (DTB)` and set **Out-of-tree Device Tree Source file paths** to the RPI's `.dts` file (`/work/crosscon/rpi4-ws/rpi4.dts`) (Theoretically this step is optional as you can also compile the Device Tree Source file into a Device Tree Blob file yourself. The lloader script simply needs the `.dtb` file. Incorporating the compile process into the Buildroot is more elegant IMHO.)
- **Target packages**:
    - Enable `BusyBox` if not already enabled
    - Keep the default **BusyBox configuration file** and additionally set **Additional BusyBox configuration fragment files** to `/work/crosscon/buildroot/build-aarch64/busybox-additional.config` to make BusyBox include additional packages like *modinfo*, etc.
    - Enable `Show packages that are also provided by busybox`
    - **Development Tools** (all optional):
        - Enable `gawk`
        - Enable `make`
        - Enable `sed`
        - Enable `tree`
    - **Hardware Handling** -> **Firmware**:
        - Enable `brcmfmac-sdio-firmware-rpi` (This is the main firmware required for the wifi chip to work as it contains its driver)
        - Enable `brcmfmac-sdio-firmware-rpi-wifi`
    - **Interpreter languages and scripting**:
        - Enable `python3` (This is very important. Our shared memory protocol runs via a python script. Without python3 we can not communicate with nexmon_csi over memory)
            - Set **python3 module format to install** to `.pyc compiled sources only`
            - Under **core python3 modules**:
                - Enable `ssl` (optional)
                - Enable `unicodedata-module` (50/50 whether needed or not, so just keep it)
                - Enable `xz module` (optional)
                - Enable `zlib module` (optional)
    - **Networking applications**:
        - Enable `crda` (Used for regulatory compliance for wifi communication)
        - Enable (`dhcp` (ISC) and `dhcp_client`) OR/AND `dhcpcd`. (Either is fine, we just need a dhcp on the RPI. Though that actually might not be true. A dhcp is only needed if you ever plan to connect a wifi the regular way. If you just want to use nexmon to gather csi data, I don't think you need a dhcp service)
        - Enable `ifupdown-scripts` (Allows us to set *up* network interfaces like our wifi interface)
        - Enable `iw` (Allows us to search for surrounding wifi networks and to create a wifi monitor interface which is required for nexmon_csi)
	- Enable `tcpdump` (Used for manual testing of nexmon_csi)
	- Enable `wireless-regdb` (Delivers the regulatory compliance database)
        - Enable `wpa_supplicant`:	(should also be optional and only be needed if you plan to connect to a wifi the regular and not use nexmon_csi)
            - Enable `nl80211 support`
            - Enable `autoscan`
            - Enable `syslog support`
            - Enable `WPS`
            - Enable `WPA3_support`
            - Enable `Install wpa_cli binary`
            - Enable `Install wpa_passphrase binary` (If you plan to connect to a wifi, then this is very important as we can use it to store the wifi's password)
    - **Security**:
        - Enable `urandom-initscripts` (unsure whether actually needed, but better seeding of RNG's is always important)
    - **System tools**:
        - Enable `kmod` (Might be required to properly handle kernel modules)
        - Enable `kmod utilites`
    - **Text editors and viewers** (all optional):
        - Enable `nano`
        - Enable `optimize for size`
        - Enable `vim`
        - Enable `install runtime`
- **Filesystem images**:
    - Enable `cpio the root filesystem (for use as an initial RAM filesystem)`
    - Set **cpio type** to `cpio the whole root filesystem`
    - Set **Compression method** to `no compression`
    - Enable `initial RAM filesystem linked into linux kernel` (Very important. The first setting creates a `rootfs.cpio` file located under `build-aarch64/images`. With this setting we advise the kernel to compile this file inside the kernel Image. See [next section](#changes-in-buildroot-kernel-config-linux-aarch64config) on how to link to that file). <br>With this change, all changes while inside the VM are volatile and will not persist between boots as filesystem is then read only.
- **External options**:
    - Enable `nexmon` (This ships the nexmon_csi software onto the VM filesystem)
    - Enable `automatic nexmon client` (This ships mechanisms for the shared memory protocol for nexmon_csi communication onto the VM filesystem)

### Changes in Buildroot kernel config [`linux-aarch64.config`](nexmon_automated_demo/linux-aarch64.config)
Whereas in my last guide, describing how to integrate wifi in your Linux VM, I explained which changes you would have to apply to `linux.config` via `make O=build-aarch64 linux-menuconfig`, in this guide we have to do it differently.
Last time our ground base for incorporating changes to `linux.config` was `support/linux-aarch64.config` retrieved from 3mdeb's fork of this DEMO reposiotory.
Since nexmon_csi contains a kernel module (`brcmfmac.ko`) which was compiled for a very specific kernel version only (5.10.92-v8+), we have to use the same kernel configuration file which we used to create the precompiled kernel module.
Unfortunately, just using the exact same doesn't suffice as well, rather we have to add/change some specific CONFIG flags in the configuration file manually.
This is described below:

Then, how would you get the base configuration file which will further be used?
Well my approach is messy, so I encourage to just use the `linux-aarch64.config` supplied in the `nexmon_automated_demo` folder and copy it over to `build-aarch64` using:
```sh
cp /work/crosscon/nexmon_automated_demo/linux-aarch64.config /work/crosscon/buildroot/build-aarch64/linux.config
```

If you are interested in how to get the base config and how to manually apply the changes any way, look into this guide: [Creating precompiled binaries of nexmon_csi for ARM64](https://github.com/pH-Valiu/nexmon_csi_bin/blob/main/COMPILING_ARM64.md).
While following the guide, at some point you have to decide whether you want to install the kernel header libraries manually or automatically.
Take the automatic approach using `rpi-source` and extract the created `.config` file from that machine.
THIS is our ground base where the following changes will be made:
IMPORTANT NOTE: Some of those CONFIGs already exist (either in the "not set" or a value containing variant). Please insert every following config flag one by one and make sure that you don't have duplicates!!
- `CONFIG_CC_VERSION_TEXT`="aarch64-buildroot-linux-gnu-gcc.br_real (Buildroot 2025.02-117-gf0693546ab) 13.3.0" (this very much does not need to be this, everything you put in here is probably fine)
- `CONFIG_BROKEN_GAS_INST`=y
- `CONFIG_CC_HAS_ASM_GOTO_OUTPUT`=y
- `CONFIG_CC_HAS_AUTO_VAR_INIT_PATTERN`=y
- `CONFIG_CC_HAS_AUTO_VAR_INIT_ZERO`=y
- `CONFIG_GCC_VERSION`=100201
- `CONFIG_LD_VERSION`=235020000
- `CONFIG_INITRAMFS_SOURCE`="/work/crosscon/buildroot/build-aarch64/images/rootfs.cpio" (THIS IS VERY IMPORTANT)
- `CONFIG_LOCALVERSION`="-v8+"		(THIS IS VERY IMPORTANT)
- `CONFIG_CMDLINE`=""
- `CONFIG_CROSSCONHYP_SHMEM`=y		(This is not necessary but for future work important)
- `CONFIG_SERIAL_8250_LPSS`=y
- `CONFIG_SERIAL_8250_MID`=y
- `CONFIG_SERIAL_8250_TEGRA`=y
- `CONFIG_SERIAL_8250_MT6577`=y
- `CONFIG_SERIAL_8250_UNIPHIER`=y
- `CONFIG_SERIAL_8250_OMAP`=y
- `CONFIG_SERIAL_8250_OMAP_TTYO_FIXUP`=y
- `CONFIG_SERIAL_8250_DW`=y
- `CONFIG_SERIAL_8250_DWLIB`=y
- `CONFIG_SERIAL_8250_NR_UARTS`=4	(This is important)
- `CONFIG_SERIAL_8250_RUNTIME_UARTS`=4	(This is important)
- `CONFIG_SERIAL_8250_DMA`=y
- `CONFIG_SERIAL_8250_DEPRECATED_OPTIONS`=y

Those following additions/changes are probably not needed but I was too lazy to double check:
- `CONFIG_NUMA_BALANCING`=y
- `CONFIG_NUMA_BALANCING_DEFAULT_ENABLED`=y
- `CONFIG_USE_PERCPU_NUMA_NODE_ID`=y
- `CONFIG_NUMA`=y
- `CONFIG_ACPI_NUMA`=y
- `CONFIG_OF_NUMA`=y
- `CONFIG_DMA_PERNUMA_CMA`=y


Now, copy our modified file into `/work/crosscon/buildroot/build-aarch64` as `linux.config` using:
```sh
cp your_modified_linux_configuration.config /work/crosscon/buildroot/build-aarch64/linux.config
```


### File contents of [`busybox-additional.config`](nexmon_automated_demo/busybox-additional.config)
In the [Buildroot config](#changes-in-buildroot-config-br-aarch64config) we already linked to this file. This file configures BusyBox to install additional modules not enabled by default, especially binaries related to handling kernel modules like *modprobe* and *lsmod*. In the following you see the contents of our `busybox-additional.config` file.
It's best to initially place this file under `/work/crosscon/support/busybox-additional.config`, then copy it over to the `build-aarch64` directory using: 
```
cp /work/crosscon/support/busybox-additional.config /work/crosscon/buildroot/build-aarch64/busybox-additional.config
```

Or just directly copy it from `nexmon_automated_demo` folder via:
```sh
cp /work/crosscon/nexmon_automated_demo/busybox-additional.config /work/crosscon/buildroot/build-aarch64/busybox-additional.config
```

The file's contents:
```conf
########################################
#
# BusyBox additional modules
#
########################################


#
# Linux Module Utilites
#

CONFIG_DEPMOD=y
CONFIG_INSMOD=y
CONFIG_LSMOD=y
CONFIG_FEATURE_LSMOD_PRETTY_2_6_OUTPUT=y
CONFIG_RMMOD=y
CONFIG_MODINFO=y
CONFIG_MODPROBE=y
```

### Changes in CROSSCON Hypervisor config [`config.c`](nexmon_automated_demo/config.c)
Last, since nexmon_csi needs wifi and our custom protocol uses CROSSCON Hypervisor shared memory at a certain location with a certain size, we need to modify [config.c](rpi4-ws/configs/rpi4-single-vTEE/config.c) to incorporate these changes.

You have the option to either:
- Copy `/work/crosscon/nexmon_automated_demo/config.c` over into `/work/crosscon/rpi4-ws/configs/rpi4-single-vTEE/config.c` with this command:
```sh
cp /work/crosscon/nexmon_automated_demo/config.c /work/crosscon/rpi4-ws/configs/rpi4-single-vTEE/config.c
```
- Or apply the changes manually to the existing file in `/work/crosscon/rpi4-ws/configs/rpi4-single-vTEE/config.c`

Since the first approach is very straightforward, I will show what changes you'd have to do:

#### Adding wifi
In the RPI's device tree [rpi4.dts](rpi4-ws/rpi4.dts) we find the wifi module as:
```dts
sdhci@7e300000 {
			compatible = "brcm,bcm2835-sdhci";
			reg = <0x7e300000 0x100>;
			interrupts = <0x00 0x7e 0x04>;
			clocks = <0x06 0x1c>;
			status = "okay";
			#address-cells = <0x01>;
			#size-cells = <0x00>;
			pinctrl-names = "default";
			pinctrl-0 = <0x0e>;
			bus-width = <0x04>;
			non-removable;
			mmc-pwrseq = <0x0f>;

			wifi@1 {
				reg = <0x01>;
				compatible = "brcm,bcm4329-fmac";
			};
		};
```
To add a new device to a VM, we need to follow the configurations described in the CROSSCON Hypervisor documentation. Hence, we need to increment the `.dev_num` counter and add this device:
```c
{
    .pa   = 0x7e300000,
    .va   = 0x7e300000,
    .size = 0x100,
    .interrupt_num = 3,
    .interrupts = (irqid_t[]) {
        0, 4, 126
    }
},
```
Furthermore, since the interrupt 126 would be a duplicate, we have to remove it from the latter list and decrement its `.interrupts_num` counter.

#### Modifying shared memory
Find the sections where shared memory is being allocated and assigned:
- Line 31 in Linux VM setup
- Line 126 (assuming you have included the wifi device) in OP-TEE OS setup
- Line 158 in the global config setup

Please, at all those locations, change:
- `.size` to `0x00800000`
- `.base` to `0x09000000`

### Complete config.c file
The complete `config.c` file can be found in the [nexmon_automated_demo folder](nexmon_automated_demo/config.c) as well as 
<details>
    <summary><b>here:</b></summary>
    <pre><code>
#include &lt;config.h&gt;

// Linux Image
VM_IMAGE(linux_image, "../lloader/linux-rpi4.bin");

// Linux VM configuration
struct vm_config linux = {
    .image = {
        .base_addr = 0x20200000,
        .load_addr = VM_IMAGE_OFFSET(linux_image),
        .size = VM_IMAGE_SIZE(linux_image),
    },
    .entry = 0x20200000,

    .type = 0,

    .platform = {
        .cpu_num = 1,
        .region_num = 1,
        .regions =  (struct mem_region[]) {
            {
                .base = 0x20000000,
                .size = 0x40000000,
                .place_phys = true,
                .phys = 0x20000000
            }
        },
        .ipc_num = 1,
        .ipcs = (struct ipc[]) {
            {
                .base = 0x09000000,
                .size = 0x00800000,
                .shmem_id = 0,
            },
        },
        .dev_num = 5,
        .devs =  (struct dev_region[]) {
            {
		.pa   = 0x7e300000,
		.va   = 0x7e300000,
		.size = 0x100,
		.interrupt_num = 3,
		.interrupts = (irqid_t[]) {
		    0, 4, 126
		}
	    },
	    {
                .pa   = 0xfc000000,
                .va   = 0xfc000000,
                .size = 0x03000000,

            },
            {
                .pa   = 0x600000000,
                .va   = 0x600000000,
                .size = 0x200000000,

            },
            {
                .interrupt_num = 183,
                .interrupts = (irqid_t[]) {
                    32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46,
                    47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61,
                    62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76,
                    77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91,
                    92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104,
                    105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116,
                    117, 118, 119, 120, 121, 122, 123, 124, 125, 127, 128,
                    129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140,
                    141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152,
                    153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164,
                    165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176,
                    177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188,
                    189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200,
                    201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212,
                    213, 214, 215, 216, 
                }
            },
            {
                /* Arch timer interrupt */
                .interrupt_num = 1,
                .interrupts = (irqid_t[]) {27}
            }
        },
        .arch = {
            .gic = {
                .gicd_addr = 0xff841000,
                .gicc_addr = 0xff842000,
            }
        }
    }
};

VM_IMAGE(optee_os_image, "../optee_os/optee-rpi4/core/tee-pager_v2.bin");


struct vm_config optee_os = {
    .image = {
        .base_addr = 0x10100000,
        .load_addr = VM_IMAGE_OFFSET(optee_os_image),
        .size = VM_IMAGE_SIZE(optee_os_image),
    },
    .entry = 0x10100000,
    .cpu_affinity = 0xf,


    .type = 1,

    .children_num = 1,
    .children = (struct vm_config*[]) { &linux },
    .platform = {
        .cpu_num = 1,
        .region_num = 1,
        .regions = (struct mem_region[]) {
            {
                .base = 0x10100000,
                .size = 0x00F00000, // 15 MB
                .place_phys = true,
                .phys = 0x10100000
            }
        },
        .ipc_num = 1,
        .ipcs = (struct ipc[]) {
            {
                .base = 0x09000000,
                .size = 0x00800000,
                .shmem_id = 0,
            }
        },
        .dev_num = 1,
        .devs = (struct dev_region[]) {
            {
                /* UART1 */
                .pa = 0xfe215000,
                .va = 0xfe215000,
                .size = 0x1000,
            },
            {
                /* Arch timer interrupt */
                .interrupt_num = 1,
                .interrupts = (irqid_t[]) {27}
            }
        },
        .arch = {
            .gic = {
                .gicd_addr = 0xff841000,
                .gicc_addr = 0xff842000,
            }
        }
    },
};

struct config config = {

    CONFIG_HEADER
    .shmemlist_size = 1,
    .shmemlist = (struct shmem[]) {
        [0] = { .size = 0x00800000, },
    },
    .vmlist_size = 1,
    .vmlist = {
        &optee_os
    }
};
    </code></pre>
</details>


## **Building**
Now, let's build the filesystem and kernel, the VM and finally the full CROSSCON Hypervisor.

### Requirements
If you have followed the sections above correctly, then `build-aarch64` should look like this:
```
build-aarch64/
|   .config
|   linux.config
|   busybox-additional.config
|___________________
```
Additionally, `/work/crosscon/rpi4-ws/configs/rpi4-single-vTEE/config.c` must have been updatedd. See [this section](#changes-in-crosscon-hypervisor-config-configc).
Additionally, `/work/crosscon/custom_applications` with all its subfolders and files has to exist. See [this section](#adding-custom-applications).

A quick overview of the next steps:
1. Setup firmware components
2. Build the OP-TEE OS
3. Invoke Buildroot (will fail)
4. Build additional packages (OP-TEE client, malicious TA, ...)
5. Invoke Buildroot again
6. Use lloader to combine the `Image` and `rpi4.dtb` to build `linux-rpi4.bin`
7. Build `crossconhyp.bin` using the `config.c` and `linux-rpi4.bin` file (and OP-TEE OS binary)
8. In an already working CROSSCON-Hypervisor RPI setup with pre-filled SD-Card, just replace `crossconhyp.bin`, otherwise make sure to copy all required files.

### Step 0 - Starting point
Start at `cd /work/crosscon` and set ``export ROOT=`pwd` ``

### Step 1 - Setup firmware components
This step can be left out if the firmware files are already on the SD-Card.
```sh
cd rpi4-ws
export RPI4_WS=`pwd`

mkdir bin

git clone https://github.com/raspberrypi/firmware.git --depth 1 --branch 1.20230405

git clone https://github.com/u-boot/u-boot.git --depth 1 --branch v2022.10
cd u-boot
make rpi_4_defconfig
make -j`nproc`  CROSS_COMPILE=aarch64-none-elf-
cp -v u-boot.bin ../bin/
cd $RPI4_WS

git clone https://github.com/bao-project/arm-trusted-firmware.git --branch bao/demo --depth 1
cd arm-trusted-firmware
make PLAT=rpi4 -j`nproc`  CROSS_COMPILE=aarch64-none-elf-
cp -v build/rpi4/release/bl31.bin ../bin/
cd $ROOT
```

Now copy all firmware inside a directory that will later fill out the RPI's SD-Card. If this is your first run ever installing the CROSSCON-Hypervisor, please refer to **rpi4-ws/README.md** on how to properly format the SD-Card.
Following code is not executed inside the docker container but rather on your normal machine.
We will assume that directory will be called `sd_card_transfer_directory` and our docker container is called `crosscon_hv_container`.
```sh
cd sd_card_transfer_directory

docker cp crosscon_hv_container:/work/crosscon/rpi4-ws/firmware/boot/. .
docker cp crosscon_hv_container:/work/crosscon/rpi4-ws/config.txt .
docker cp crosscon_hv_container:/work/crosscon/rpi4-ws/bin/bl31.bin .
docker cp crosscon_hv_container:/work/crosscon/rpi4-ws/bin/u-boot.bin .
```

### Step 2 - Building the OP-TEE OS
```sh
cd optee_os

OPTEE_DIR="./"
export O="$OPTEE_DIR/optee-rpi4"
CC="aarch64-none-elf-"
export CFLAGS=-Wno-cast-function-type
PLATFORM="rpi4"
ARCH="arm"
SHMEM_START="0x08000000"
SHMEM_SIZE="0x00200000"
TZDRAM_START="0x10100000"
TZDRAM_SIZE="0x00F00000"
CFG_GIC=n

rm -rf $O

make -C $OPTEE_DIR \
    O=$O \
    CROSS_COMPILE=$CC \
    PLATFORM=$PLATFORM \
    PLATFORM_FLAVOR=$PLATFORM_FLAVOR \
    ARCH=$ARCH \
    CFG_PKCS11_TA=n \
    CFG_SHMEM_START=$SHMEM_START \
    CFG_SHMEM_SIZE=$SHMEM_SIZE \
    CFG_CORE_DYN_SHM=n \
    CFG_NUM_THREADS=1 \
    CFG_CORE_RESERVED_SHM=y \
    CFG_CORE_ASYNC_NOTIF=n \
    CFG_TZDRAM_SIZE=$TZDRAM_SIZE \
    CFG_TZDRAM_START=$TZDRAM_START \
    CFG_GIC=y \
    CFG_ARM_GICV2=y \
    CFG_CORE_IRQ_IS_NATIVE_INTR=n \
    CFG_ARM64_core=y \
    CFG_USER_TA_TARGETS=ta_arm64 \
    CFG_DT=n \
    CFG_CORE_ASLR=n \
    CFG_CORE_WORKAROUND_SPECTRE_BP=n \
    CFG_CORE_WORKAROUND_NSITR_CACHE_PRIME=n \
    CFG_TEE_CORE_LOG_LEVEL=1 \
    DEBUG=1 -j16


OPTEE_DIR="./"
export O="$OPTEE_DIR/optee2-rpi4"
SHMEM_START="0x08200000"
TZDRAM_START="0x20100000"

rm -rf $O

make -C $OPTEE_DIR \
    O=$O \
    CROSS_COMPILE=$CC \
    PLATFORM=$PLATFORM \
    PLATFORM_FLAVOR=$PLATFORM_FLAVOR \
    ARCH=$ARCH \
    CFG_PKCS11_TA=n \
    CFG_SHMEM_START=$SHMEM_START \
    CFG_SHMEM_SIZE=$SHMEM_SIZE \
    CFG_CORE_DYN_SHM=n \
    CFG_CORE_RESERVED_SHM=y \
    CFG_CORE_ASYNC_NOTIF=n \
    CFG_TZDRAM_SIZE=$TZDRAM_SIZE \
    CFG_TZDRAM_START=$TZDRAM_START \
    CFG_GIC=y \
    CFG_ARM_GICV2=y \
    CFG_CORE_IRQ_IS_NATIVE_INTR=n \
    CFG_ARM64_core=y \
    CFG_USER_TA_TARGETS=ta_arm64 \
    CFG_DT=n \
    CFG_CORE_ASLR=n \
    CFG_CORE_WORKAROUND_SPECTRE_BP=n \
    CFG_CORE_WORKAROUND_NSITR_CACHE_PRIME=n \
    CFLAGS="${CFLAGS} -DOPTEE2" \
    CFG_EARLY_TA=y \
    CFG_TEE_CORE_LOG_LEVEL=1 \
    DEBUG=1 -j16

cd $ROOT
```

### Step 3 - Invoke Buildroot
This step can take very long. Wait for it to fail! (It fails because the additional OP-TEE client binaries, etc., are not yet existing)
```sh
cd buildroot

export FORCE_UNSAFE_CONFIGURE=1
make O=build-aarch64 BR2_EXTERNAL=/work/crosscon/custom_applications -j`nproc`

cd $ROOT
```

### Step 4 - Build additional packages
We will build:
- OP-TEE Clients
- OP-TEE xtests
- Bitcoin Wallet Client and Trusted Application
- Malicious Client and Trusted Application

I don't think any of these are necessary for our nexmon_csi VM but whatever.
``` sh
cd optee_client

git checkout master
make CROSS_COMPILE=aarch64-none-linux-gnu- WITH_TEEACL=0 O=out-aarch64
git checkout optee2
make CROSS_COMPILE=aarch64-none-linux-gnu- WITH_TEEACL=0 O=out2-aarch64

cd $ROOT


cd optee_test

BUILDROOT=`pwd`/../buildroot/build-aarch64/
export CROSS_COMPILE=$BUILDROOT/host/bin/aarch64-linux-
export HOST_CROSS_COMPILE=$BUILDROOT/host/bin/aarch64-linux-
export TA_CROSS_COMPILE=$BUILDROOT/host/bin/aarch64-linux-
export ARCH=aarch64
export PLATFORM=plat-vexpress
export PLATFORM_FLAVOR=qemu_armv8a
export TA_DEV_KIT_DIR=`pwd`/../optee_os/optee-rpi4/export-ta_arm64
export TEEC_EXPORT=`pwd`/../optee_client/out-aarch64/export/usr/
export OPTEE_CLIENT_EXPORT=`pwd`/../optee_client/out-aarch64/export/usr/
export CFG_TA_OPTEE_CORE_API_COMPAT_1_1=y
export DESTDIR=./to_buildroot-aarch64
export DEBUG=0
export CFG_TEE_TA_LOG_LEVEL=0
export CFLAGS=-O2
export O=`pwd`/out-aarch64
export CFG_PKCS11_TA=n

rm -rf $O
rm -rf to_buildroot-aarch64/
find . -name "Makefile" -exec sed -i "s/\-lteec2$/\-lteec/g" {} +
find . -name "Makefile" -exec sed -i "s/optee2_armtz/optee_armtz/g" {} +
make clean
make -j`nproc`
make install


export O=`pwd`/out2-aarch64
export DESTDIR=./to_buildroot-aarch64-2
export TA_DEV_KIT_DIR=`pwd`/../optee_os/optee2-rpi4/export-ta_arm64
export TEEC_EXPORT=`pwd`/../optee_client/out2-aarch64/export/usr/
export OPTEE_CLIENT_EXPORT=`pwd`/../optee_client/out2-aarch64/export/usr/
rm -rf `pwd`/out2-aarch64
find . -name "Makefile" -exec sed -i "s/\-lteec$/\-lteec2/g" {} +
find . -name "Makefile" -exec sed -i "s/optee_armtz/optee2_armtz/g" {} +
make clean
make -j`nproc`
make install
find . -name "Makefile" -exec sed -i "s/\-lteec2$/\-lteec/g" {} +
find . -name "Makefile" -exec sed -i "s/optee2_armtz/optee_armtz/g" {} +

mv $DESTDIR/bin/xtest $DESTDIR/bin/xtest2
cd $ROOT


cd bitcoin-wallet

BUILDROOT=`pwd`/../buildroot/build-aarch64/

export CROSS_COMPILE=$BUILDROOT/host/bin/aarch64-linux-
export HOST_CROSS_COMPILE=$BUILDROOT/host/bin/aarch64-linux-
export TA_CROSS_COMPILE=$BUILDROOT/host/bin/aarch64-linux-
export ARCH=aarch64
export PLATFORM=plat-virt
export TA_DEV_KIT_DIR=`pwd`/../optee_os/optee-rpi4/export-ta_arm64
export TEEC_EXPORT=`pwd`/../optee_client/out-aarch64/export/usr/
export OPTEE_CLIENT_EXPORT=`pwd`/../optee_client/out-aarch64/export/usr/
export CFG_TA_OPTEE_CORE_API_COMPAT_1_1=n
export DESTDIR=./to_buildroot-aarch64
export DEBUG=0
export CFG_TEE_TA_LOG_LEVEL=0
export O=`pwd`/out-aarch64

rm -rf out-aarch64/
## make sure we have things setup for first OP-TEE
find . -name "Makefile" -exec sed -i "s/\-lteec2$/\-lteec/g" {} +
find . -name "Makefile" -exec sed -i "s/optee2_armtz/optee_armtz/g" {} +
make clean
make -j`nproc`

mkdir -p to_buildroot-aarch64/lib/optee_armtz
mkdir -p to_buildroot-aarch64/bin

cp out-aarch64/*.ta to_buildroot-aarch64/lib/optee_armtz
cp host/wallet to_buildroot-aarch64/bin/bitcoin_wallet_ca
chmod +x to_buildroot-aarch64/bin/bitcoin_wallet_ca

## setup second OP-TEE
export O=`pwd`/out2-aarch64
export DESTDIR=./to_buildroot-aarch64-2
export TA_DEV_KIT_DIR=`pwd`/../optee_os/optee2-rpi4/export-ta_arm64
export TEEC_EXPORT=`pwd`/../optee_client/out2-aarch64/export/usr/
export OPTEE_CLIENT_EXPORT=`pwd`/../optee_client/out2-aarch64/export/usr/
rm -rf `pwd`/out2-aarch64
find . -name "Makefile" -exec sed -i "s/\-lteec/\-lteec2/g" {} +
find . -name "Makefile" -exec sed -i "s/optee_armtz/optee2_armtz/g" {} +
make clean
make -j`nproc`
## undo changes
find . -name "Makefile" -exec sed -i "s/\-lteec2/\-lteec/g" {} +
find . -name "Makefile" -exec sed -i "s/optee2_armtz/optee_armtz/g" {} +

mkdir -p to_buildroot-aarch64-2/lib/optee2_armtz
mkdir -p to_buildroot-aarch64-2/bin

cp out-aarch64/*.ta to_buildroot-aarch64-2/lib/optee2_armtz
cp host/wallet to_buildroot-aarch64-2/bin/bitcoin_wallet_ca2
chmod +x to_buildroot-aarch64-2/bin/bitcoin_wallet_ca2


cd $ROOT


cd malicous_ta
BUILDROOT=`pwd`/../buildroot/build-aarch64/
export CROSS_COMPILE=$BUILDROOT/host/bin/aarch64-linux-
export HOST_CROSS_COMPILE=$BUILDROOT/host/bin/aarch64-linux-
export TA_CROSS_COMPILE=$BUILDROOT/host/bin/aarch64-linux-
export ARCH=aarch64
export PLATFORM=plat-virt
export TA_DEV_KIT_DIR=`pwd`/../optee_os/optee-rpi4/export-ta_arm64
export TEEC_EXPORT=`pwd`/../optee_client/out-aarch64/export/usr/
export OPTEE_CLIENT_EXPORT=`pwd`/../optee_client/out-aarch64/export/usr/
export CFG_TA_OPTEE_CORE_API_COMPAT_1_1=n
export DESTDIR=./to_buildroot-aarch64
export DEBUG=0
export CFG_TEE_TA_LOG_LEVEL=2
export O=`pwd`/out-aarch64
export aarch64_TARGET=y 
rm -rf out-aarch64/
## make sure we have things setup for first OP-TEE
find . -name "Makefile" -exec sed -i "s/\-lteec2$/\-lteec/g" {} +
find . -name "Makefile" -exec sed -i "s/optee2_armtz/optee_armtz/g" {} +
make clean
make -j`nproc`
mkdir -p to_buildroot-aarch64/lib/optee_armtz
mkdir -p to_buildroot-aarch64/bin
cp out-aarch64/*.ta to_buildroot-aarch64/lib/optee_armtz
cp host/malicious_ca to_buildroot-aarch64/bin/malicious_ca
chmod +x to_buildroot-aarch64/bin/malicious_ca
## setup second OP-TEE
export O=`pwd`/out2-aarch64
export DESTDIR=./to_buildroot-aarch64-2
export TA_DEV_KIT_DIR=`pwd`/../optee_os/optee2-rpi4/export-ta_arm64
export TEEC_EXPORT=`pwd`/../optee_client/out2-aarch64/export/usr/
export OPTEE_CLIENT_EXPORT=`pwd`/../optee_client/out2-aarch64/export/usr/
rm -rf `pwd`/out2-aarch64
find . -name "Makefile" -exec sed -i "s/\-lteec/\-lteec2/g" {} +
find . -name "Makefile" -exec sed -i "s/optee_armtz/optee2_armtz/g" {} +
make clean
make -j`nproc`
## undo changes
find . -name "Makefile" -exec sed -i "s/\-lteec2/\-lteec/g" {} +
find . -name "Makefile" -exec sed -i "s/optee2_armtz/optee_armtz/g" {} +
mkdir -p to_buildroot-aarch64-2/lib/optee2_armtz
mkdir -p to_buildroot-aarch64-2/bin
cp out2-aarch64/*.ta to_buildroot-aarch64-2/lib/optee2_armtz
cp host/malicious_ca to_buildroot-aarch64-2/bin/malicious_ca2
chmod +x to_buildroot-aarch64-2/bin/malicious_ca2
cd $ROOT
```

### Step 5 - Finish Buildroot
```sh
cd buildroot

export FORCE_UNSAFE_CONFIGURE=1
make O=build-aarch64 BR2_EXTERNAL=/work/crosscon/custom_applications -j`nproc`

cd $ROOT
```

### Step 6 - Build linux binary with lloader
```sh
cd lloader
rm linux-rpi4.bin
rm linux-rpi4.elf
make  \
    IMAGE=../buildroot/build-aarch64/images/Image \
    DTB=../buildroot/build-aarch64/images/rpi4.dtb \
    TARGET=linux-rpi4.bin \
    CROSS_COMPILE=aarch64-none-elf- \
    ARCH=aarch64

cd $ROOT
```

### Step 7 - Build crossconhyp.bin
```sh
CONFIG_REPO=/work/crosscon/rpi4-ws/configs

make -C CROSSCON-Hypervisor/ \
	PLATFORM=rpi4 \
	CONFIG_BUILTIN=y \
	CONFIG_REPO=$CONFIG_REPO \
	CONFIG=rpi4-single-vTEE \
	OPTIMIZATIONS=0 \
        SDEES="sdSGX sdTZ" \
	CROSS_COMPILE=aarch64-none-elf- \
        clean

make -C CROSSCON-Hypervisor/ \
	PLATFORM=rpi4 \
	CONFIG_BUILTIN=y \
	CONFIG_REPO=$CONFIG_REPO \
	CONFIG=rpi4-single-vTEE \
	OPTIMIZATIONS=0 \
        SDEES="sdSGX sdTZ" \
	CROSS_COMPILE=aarch64-none-elf- \
        -j`nproc`
```

Now copy `crossconhyp.bin` inside the directory that will later fill out the RPI's SD-Card.
Following code is not executed inside the docker container but rather on your normal machine.
We will assume that directory will be called `sd_card_transfer_directory` and our docker container is called `crosscon_hv_container`.
```sh
cd sd_card_transfer_directory

docker cp crosscon_hv_container:/work/crosscon/CROSSCON-Hypervisor/bin/rpi4/builtin-configs/rpi4-single-vTEE/crossconhyp.bin .
```

### Step 8 - Copy to SD-Card
Now copy all contents of `sd_card_transfer_directory` into the SD_Card (or only `crossconhyp.bin`).<br>
Connect to the RPI with a UART-USB-Converter with baudrate 115200 with the RPI being also plugged in to normal power supply.<br>
Hit Ctrl-C until u-boot comes up.<br>
Enter: 
```
fatload mmc 0 0x200000 crossconhyp.bin; go 0x200000
```
 to start the hypervisor and login using `root`.


## Testing
To test the nexmon_csi software you have two options.
Either do manual testing while having a shell inside the VM, or use the protocol to communicate with nexmon_csi over shared memory.
For the latter case, since we currently don't have a third VM who could write into shared memory to act as our interface, we simulate it using `devmem` while having a shell inside our nexmon VM.

### Manual nexmon csi testing
Load the wifi module:
```
modprobe brcmfmac
```
If successful, the module will be visible under `lsmod` and you might have gotton a kernel log which says sth about nexmon as well.

Now:
1. Use makecsiparams to generate a base64 encoded parameter string that can be used to configure the extractor.
   The following example call generates a parameter string that enables collection on channel 12 with 20 MHz bandwidth on the first core for the first spatial stream
    ```
    makecsiparams -c 12/20 -C 1 -N 1
    m+IBEQGIAgAAESIzRFWqu6q7qrsAAAAAAAAAAAAAAAAAAA== (different for you)
    ```
   For a full list of possible parameters run `makecsiparams -h`.
2. make sure wpa_supplicant is not running: `pkill wpa_supplicant`
3. Make sure your interface is up: `ifconfig wlan0 up` (replace wlan0 with your interface name)
4. Configure the extractor using nexutil and the generated parameters (adapt the argument of -v with your parameters):
    ```
    nexutil -Iwlan0 -s500 -b -l34 -vm+IBEQGIAgAAESIzRFWqu6q7qrsAAAAAAAAAAAAAAAAAAA==
    ```
5. Enable monitor mode:
    ```
    iw phy `iw dev wlan0 info | gawk '/wiphy/ {printf "phy" $2}'` interface add mon0 type monitor
    ifconfig mon0 up
    ```
If you don't have gawk installed, do it manually. (e.g. `iw phy phy0 interface add mon0 type monitor`)

6. Collect CSI by listening on UDP socket 5500, e.g. by using tcpdump: `tcpdump -i wlan0 dst port 5500`. There will be one UDP packet per configured core and spatial stream for each incoming frame.

### Shared memory protocol for communication
This part is split into two sections.
- First, how the protocol is defined
- Second, how it is used and accessed

#### Protocol definition
Our protocol uses the shared memory at the VM's physical address `0x09000000` having a size of `0x00800000` bytes (around 8MiB).

The memory is split into two sections:
- The first **312** bytes are for configuration parameters and return flags and meta informations.
- The remaining byte area is used to transfer the acquired csi data, where each sample has a size of **267** Bytes.

Multi-Byte data types (e.g. uint_16 or uint_32) are in BigEndianess layout.
 
Each Sample is structed like this:
|    Bytes    |  Data type  |      Usage      |
|-------------|-------------|-----------------|
| **0**       | 1* uint_8   | RSSI            |
| **1-6**     | 6* uint_8   | MAC             |
| **7-8**     | 1* uint_16  | StreamId        |
| **9-10**    | 1* uint_16  | TimeOffset (s)  |
| **11-266**  | 256* uint_8 | Data            |

The Parameter section is structured like this:
|    Bytes    |    Data type    |                Usage                |
|-------------|-----------------|-------------------------------------|
| **0**	      | 1* uint_8       | Flags: 0bx00000yz -> see below      |
| **1**       | 1* uint_8       | Wifi Channel to listen on           |
| **2**       | 1* uint_8       | Channel Bandwidth in MHz            |
| **3**       | 1* uint_8       | # Samples per Device                |
| **4-5**     | 1* uint_16      | Timeout in seconds                  |
| **6**       | 1* uint_8       | Number of Devices resp. MACs (=)    |
| **7**       | 1* uint_8       | Return value                        |
| **8-11**    | 1* uint_32      | # Retrieved total Samples           |
| **12-311**  | 300* uint_8     | MACs to filter for (=)              |

Flags is one byte: **0bx00000yz** where:
- **x**: set to 1 if MAC filter shall be active, 0 if not
- **y**: 1 when nexmon_csi data gathering has finished, 0 if still active or not running
- **z**: set to 1 to start nexmon_csi data gathering, is being set 0 when finished.

There are three different execution variants:

**MAC filter is on:**
- Data gathering will finish if for all `Number of MACs` many devices `# Samples per Device` many samples have been gathered or `Timeout` was hit.
- If `Number of MACs` exceeds MAX_DEVICES (*50*) then return is **1**.
- If combination of `Number of MACs` and `# Samples per Device` exceeds DATA_MEMORY_MAX_SIZE, then return is **2**.
- Only samples, whose MAC is one of `MACs to filter for`, are being collected.
- A device can never store more samples than `# Samples per Device`.
- Parameters marked with `(=)` are only being used in this execution mode. Otherwise they are irrelevant.

**MAC filter is off and `# Samples per Device` is not Zero:**
- Data gathering will finish if `Timeout` was hit or over all collected devices the total number of collected samples exceeds DATA_MAX_SAMPLES.
- Each found device can never store more samples than `# Samples per Device`.

**MAC filter is off and `# Samples per Device` is Zero:**
- Data gathering will finish if `Timeout` was hit or over all collected devices the total number of collected samples exceeds DATA_MAX_SAMPLES.
- Each found device can store oup to DATA_MAX_SAMPLES many samples.

During data gathering, the LED of the RPI turns on. When finished it turns off again.

`# Retrieved total Samples` contains the total number of retrieved samples after data gathering has finished.

Return value can be:
- 0:      Doesn't occur.
- 1:      Failed, due to number_of_macs specified exceeding MAX_DEVICES
- 2:      Failed, due to combination of samples_per_device and number_of_macs exceeding DATA_MEMORY_MAX_SIZE (only valid if mac filter is on)
- 3:      Failed, due to a failing subprocess during nexmon configuration
- 4:      Failed, due to a generic exception during nexmon configuration
- 5:      Failed, due to a generic exception during main loop
- 6:      Succeeded, with Active MAC filter due to all samples collected
- 7:      Succeeded, due to timeout
- 8:      Succeeded, with INActive MAC filter due to DATA_MAX_SAMPLES hit
- 9:      Failed, due to unforseen reason during data gathering
- 10:     Failed, due to failed aligned writing to devmem
- 11:     Doesn't occur. Used to internally indicate starting bit NOT set
- 12:     Failed, due to failed aligned reading from devmem

#### Protocol usage in production
During startup of our VM [S90nexmon](nexmon_automated_demo/custom_applications/package/automatic_nexmon_client/files/S90nexmon) is being called and inserts our `brcmfmac.ko` kernel module.
Then it does some small LED blinking and starts [nexmon_client.py](nexmon_automated_demo/custom_applications/package/automatic_nexmon_client/files/nexmon_client.py).

To manually test the protocol use `devmem` and use one of the following command combinations:

**Test 1:**
- Channel 6
- Bandwidth 20
- 100 Samples per Device
- 30s Timeout
- no MAC filter
```sh
devmem 0x9000000 64 0x0000001E64140601
```

**Test 2:**
- Channel 6
- Bandwidth 20
- 0 Samples per Device
- 30s Timeout
- no MAC filter
```sh
devmem 0x9000000 64 0x0000001E00140601
```

**Test 3:**
- Channel 6
- Bandwidth 20
- 100 Samples per Device
- 30s Timeout
- active MAC filter
- 1 Device / MAC
- MACs: E8:10:98:D1:8B:A0
```sh
devmem 0x9000000 64 0x0001001E64140681
devmem 0x9000008 64 0xD19810E800000000
devmem 0x9000010 64 0x000000000000A08B
```

To check/read the parameters via `devmem`, call:
```sh
devmem 0x9000000 64
```

To start reading the csi data, call and index forward:
```sh
devmem 0x9000138 64
```

## Additional notes

### Using just the linux vm
If you, for example, want to do a triple CROSSCON Hypervisor VM setup and therefore don't need `crossconhyp.bin` but just our Nexmon VM binary, then use `linux-rpi4.bin` which is being created during the [lloader step](#step-6---build-linux-binary-with-lloader).
Of course you need to modify `config.c` accordingly then.
