# Buildroot Guide - Integrating Nexmon_CSI in your Linux VM running on CROSSCON Hypervisor

This guide will show the steps required to run nexmon_csi inside a Linux VM running on the CROSSCON Hypervisor on an Raspberry PI 4.
It is heavily based on my guide on how to include wifi in the Linux VM. Actually, all steps in that prior guide (apart from the changes to `linux.config`) can be found here as well.

## **Requirements**
- Linux Kernel needs to be compiled for version 5.10.92-v8+ inside Buildroot and not externally
- We need to enable the WIFI chip in the Hypervisor config file using the rPI device tree. See [this section](#enabling-wifi-chip-in-crosscon-hypervisor-for-rpi). 

Please refer to the [nexmon_demo](nexmon_demo) folder containing multiple `config` files which can be used to assemble a working build.<br>
We will further assume that we are deploying for **aarch64** Raspberry PI 4 architecture. This guide is based on the **rpi4-ws/README.md** guide.
We encourage to do the following steps inside a docker container. Refer to **env/README.md** for how to set up the docker environment.

## Structure
1. [Configurations](#configurations):
    1. [Buildroot config](#changes-in-buildroot-config-br-aarch64config)
    2. [Linux config](#changes-in-buildroot-kernel-config-linux-aarch64config)
    3. [BusyBox config](#file-contents-of-busybox-additionalconfig)
    4. [Enable WIFI chip](#enabling-the-wifi-chip-in-crosscon-hypervisor-for-rpi)
    5. [Adding Nexmon](#adding-nexmon)
2. [Pipeline](#pipeline):
    1. [Setup firmware components](#step-1---setup-firmware-components)
    2. [Build OP-TEE OS](#step-2---building-the-op-tee-os)
    3. [Build kernel & filesystem](#step-3---invoke-buildroot)
    4. [Create CROSSCON Hypervisor](#step-7---build-crossconhypbin)
3. [Testing](#testing)

## Configurations

### Changes in Buildroot config [`br-aarch64.config`](nexmon_demo/br-aarch64.config)
How can we apply the following changes? Move to `/work/crosscon/buildroot`. 
First, we will checkout to an older version of buildroot for which we have made sure that our guide works.
```sh
git checkout 2022.11.x
```
Afterwards, invoke 
```
mkdir build-aarch64
```
and
```
make O=build-aarch64 BR2_EXTERNAL=/work/crosscon/custom_applications menuconfig
```
(We need to link our external custom_applications tree as that folder will later contain the configuration files required to include nexmon in the buildroot pipeline.<br>
As long as the future `build-aarch64/.config` is not deleted, we do not need to add `BR2_EXTERNAL=...` to future `make` calls we invoke inside the Buildroot directory.)

Now a settings menu should appear. **Load** `/work/crosscon/support/br-aarch64.config`. After you have all applied all changes, **Save** the changes in the same file. Now copy the file into `build-aarch64` using 
```sh
cp /work/crosscon/support/br-aarch64.config /work/crosscon/buildroot/build-aarch64/.config
```
<br>
Apply the following changes:

- **Target Architecture**:
    - Please make changes as required to fit your hardware. Following are the settings for the rPI:
    - Set **Target Architecture** to `AArch64 (little endian)`
    - Set **Target Architecture Variant** to `cortex-A53`
    - Set **Floating point strategy** to `FP-ARMv8`
    - Set **MMU Page Size** to `4KB`
    - Set **Target Binary Format** to `ELF`
- **Toolchain**:
    - Set the **Kernel Headers** field to the same kernel version (e.g. *5.10.x*) as you want your kernel build
- **System configuration**:
    - For **Init system**: Set `BusyBox`
    - For **/dev management**: Set `Dynamic using devtmpfs only`
    - For **Root Filesystem overlay directories**: Keep the paths to the export directories of your additional binaries until you divert to including them the proper way using the Buildroot packaging system
- **Kernel**:
    - Enable `Kernel`
    - For **Kernel Version**: Either choose a specific kernel version yourself but keep in mind that those do NOT contain the 3 commits issued by CROSSCON partners to enable "stuff". Therefore, if you want a specific valid version, you need to fork from the CROSSCON Hypervisor Demos linux repository, restore or fast-forward to the commit resembling your wanted kernel version (fast-forwarding requires setting an upstream to either the official linux kernel repository (https://github.com/torvalds/linux.git) or a repository containing stable kernel version (https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git) and forwarding to the specific commit). Afterwards, you need to cherry-pick those 3 commits on top of your kernel version commit. If any merge conflicts occur you will have to resolve them manually (use your brain). Now set your fork as the `Custom Git repository`.
    - For **Custom repository version**: Set it to the branch name of your working fork
    - For **Kernel configuration**: Set it to `Using a custom (def)config file` and specify `/work/crosscon/buildroot/build-aarch64/linux.config` as your kernel config file
    - Checkmark `Build a Device Tree Blob (DTB)` and set **Out-of-tree Device Tree Source file paths** to the rPI's `.dts` file (`/work/crosscon/rpi4-ws/rpi4.dts`) (Theoretically this step is optional as you can also compile the Device Tree Source file into a Device Tree Blob file yourself. The lloader script simply needs the `.dtb` file. Incorporating the compile process into the Buildroot is more elegant IMHO.)
- **Target packages**:
    - Enable `BusyBox` if not already enabled
    - Keep the default **BusyBox configuration file** and additionally set **Additional BusyBox configuration fragment files** to `/work/crosscon/buildroot/build-aarch64/busybox-additional.config` to make BusyBox include additional packages like *modinfo*, etc.
    - Enable `Show packages that are also provided by busybox`
    - **Hardware Handling** -> **Firmware**:
        - Enable `brcmfmac-sdio-firmware-rpi` (This is the main firmware required for the wifi chip to work as it contains its driver)
        - Enable `brcmfmac-sdio-firmware-rpi-wifi`
    - **Networking applications**:
        - Enable `crda` (Used for regulatory compliance for wifi communication)
        - Enable (`dhcp` (ISC) and `dhcp_client`) OR/AND `dhcpcd`. (Either is fine, we just need a dhcp on the rPI)
        - Enable `ifupdown-scripts` (Allows us to set *up* network interfaces like our wifi interface)
        - Enable `iw` (Allows us to search for surrounding wifi networks)
	- Enable `tcpdump` (Used for manual testing of nexmon_csi)
	- Enable `wireless-regdb` (Delivers the regulatory compliance database)
        - Enable `wpa_supplicant`:
            - Enable `nl80211 support`
            - Enable `autoscan`
            - Enable `syslog support`
            - Enable `WPS`
            - Enable `WPA3_support`
            - Enable `Install wpa_cli binary`
            - Enable `Install wpa_passphrase binary` (Very important. This allows us to set credentials for a wifi network)
    - **System tools**:
        - Enable `kmod` (Might be required to properly handle kernel modules)
        - Enable `kmod utilites`
- **Filesystem images**:
    - Enable `cpio the root filesystem (for use as an initial RAM filesystem)`
    - Set **cpio type** to `cpio the whole root filesystem`
    - Set **Compression method** to `no compression`
    - Enable `initial RAM filesystem linked into linux kernel` (Very important. The first setting creates a `rootfs.cpio` file located under `build-aarch64/images`. With this setting we advise the kernel to compile this file inside the kernel Image. See [next section](#changes-in-buildroot-kernel-config-linux-aarch64config) on how to link to that file)

### Changes in Buildroot kernel config [`linux-aarch64.config`](nexmon_demo/linux-aarch64.config)
Whereas in my last guide, describing how to integrate wifi in your Linux VM, I explained which changes you would have to apply to `linux.config` via `make O=build-aarch64 linux-menuconfig`, in this guide we have to do it differently.
Last time our ground base for incorporating changes to `linux.config` was `linux-aarch64.config` retrieved from 3mdeb's fork of this DEMO reposiotory.
Since nexmon_csi contains a kernel module (`brcmfmac.ko`) which was compiled for a very specific kernel version only (5.10.92-v8+), we have to use the same kernel configuration file which we used to create the precompiled kernel module.
Unfortunately, just using the exact same doesn't suffice as well, rather we have to add/change some specific CONFIG flags in the configuration file manually.
This is described below:

How would you get the base configuration file which will further be used?
Well my approach is messy, so I encourage to just use the `linux-aarch64.config` supplied in the `nexmon_demo` folder and copy it over to `build-aarch64` using:
```sh
cp /work/crosscon/nexmon_demo/linux-aarch64.config /work/crosscon/buildroot/build-aarch64/linux.config
```

If you are interested in how to get the base config and how to manually apply the changes any way, look into this guide: [Creating precompiled binaries of nexmon_csi for ARM64](https://github.com/pH-Valiu/nexmon_csi_bin/blob/main/COMPILING_ARM64.md).
While following the guide, at some point you have to decide whether you want to install the kernel header libraries manually or automatically.
Take the automatic approach using `rpi-source` and extract the created `.config` file from that machine.
THIS is our ground base where the following changes will be made:
IMPORTANT NOTE: Some of those configs already exist (either in the "not set" or a value containing variant). Please insert every following config flag one by one and make sure that you don't have duplicates!!
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


### File contents of [`busybox-additional.config`](nexmon_demo/busybox-additional.config)
In the [Buildroot config](#changes-in-buildroot-config-br-aarch64config) we already linked to this file. This file configures BusyBox to install additional modules not enabled by default, especially binaries related to handling kernel modules like *modprobe* and *lsmod*. Following is the contents of our `busybox-additional.config` file.
It's best to initially place this file under `/work/crosscon/support/busybox-additional.config`, then copy it over to the `build-aarch64` directory using: 
```
cp /work/crosscon/support/busybox-additional.config /work/crosscon/buildroot/build-aarch64/busybox-additional.config
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

### Enabling the WIFI chip in CROSSCON Hypervisor for rPI
We will modify `/work/crosscon/rpi4-ws/configs/rpi4-single-vTEE/config.c` so that our Linux VM has access to the wifi module.
In the rPI's device tree `rpi4.dts` we find the wifi module as:
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

The complete `config.c` file can be found in the [nexmon_demo folder](nexmon_demo/rpi4-single-vtee------config.c) as well as 
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
                .base = 0x08000000,
                .size = 0x00200000,
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
                .base = 0x08000000,
                .size = 0x00200000,
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
        [0] = { .size = 0x00200000, },
    },
    .vmlist_size = 1,
    .vmlist = {
        &optee_os
    }
};
    </code></pre>
</details>

### Adding nexmon
We add nexmon (nexmon_csi) into our Linux VM by including a precompiled version of it into the buildroot pipeline.
Copy [custom_applications](nexmon_demo/custom_applications) folder over to your working directory. e.g. `/work/crosscon`.
This directory is also the one we reference when starting the buildroot pipeline in our `make O=build-aarch64 BR2_EXTERNAL=/work/crosscon/custom_applications` command.
If you want to understand how to add custom applications, please refer to this guide [Adding custom applications](ADDING_CUSTOM_PACKAGES.md).
What is happening inside this script? We download the precompiled binaries for kernel version 5.10.92-v8+ from my github repo, extract the contents and place them at specific paths in the target system, so that these applications are reachable.

## **Pipeline**
Now, let's build the filesystem and kernel. If you have followed the sections above correctly, then `build-aarch64` should look like this:
```
build-aarch64/
|   .config
|   linux.config
|   busybox-additional.config
|___________________
```
Additionally, `/work/crosscon/rpi4-ws/configs/rpi4-single-vTEE/config.c` has to be updated to have the wifi chip be enabled. See [this section](#enabling-the-wifi-chip-in-crosscon-hypervisor-for-rpi).
Additionally, `/work/crosscon/custom_applications` with all its subfolders and files has to exist. See [this section](#adding-nexmon).

A quick overview of the next steps:
1. Setup firmware components
2. Build the OP-TEE OS
3. Invoke Buildroot (will fail)
4. Build additional packages (OP-TEE client, malicious TA, ...)
5. Invoke Buildroot again
6. Use lloader to combine the `Image` and `rpi4.dtb` to build `linux-rpi4.bin`
7. Build `crossconhyp.bin` using the `config.c` and `linux-rpi4.bin` file (and OP-TEE OS binary)
8. In an already working CROSSCON-Hypervisor rPI setup with pre-filled SD-Card, just replace `crossconhyp.bin`, otherwise make sure to copy all required files.

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

Now copy all firmware inside a directory that will later fill out the rPI's SD-Card. If this is your first run ever installing the CROSSCON-Hypervisor, please refer to **rpi4-ws/README.md** on how to properly format the SD-Card.
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
This step can take very long. Wait for it to fail!
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

Now copy `crossconhyp.bin` inside the directory that will later fill out the rPI's SD-Card.
Following code is not executed inside the docker container but rather on your normal machine.
We will assume that directory will be called `sd_card_transfer_directory` and our docker container is called `crosscon_hv_container`.
```sh
cd sd_card_transfer_directory

docker cp crosscon_hv_container:/work/crosscon/CROSSCON-Hypervisor/bin/rpi4/builtin-configs/rpi4-single-vTEE/crossconhyp.bin .
```

### Step 8 - Copy to SD-Card
Now copy all contents of `sd_card_transfer_directory` into the SD_Card (or only `crossconhyp.bin`).<br>
Connect to the rPI with a UART-USB-Converter with baudrate 115200 with the rPI being also plugged in to normal power supply.<br>
Hit Ctrl-C until u-boot comes up.<br>
Enter: 
```
fatload mmc 0 0x200000 crossconhyp.bin; go 0x200000
```
 to start the hypervisor and login using `root`.


## Testing
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
