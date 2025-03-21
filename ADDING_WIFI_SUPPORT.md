# How to add wifi support

Still in progress for how to do achieve this

in menuconfig of buildrooot I enabled the brcm firmware package
under Target Packages -> Hardware Handling -> Firmware -> brcmfmac-sdio-firmware-rpi and the succeeding brcmfmac-sdio-firmware-rpi-wifi option

one other thing was to have `CONFIG_BRCMFMAC=y` enabled in the linux kernel config file as well as `CONFIG_MODULES=y` and `CONFIG_MODULES_UNLOAD=y`

now since that also did not do the trick, lets try building the kernel through buildroot.
