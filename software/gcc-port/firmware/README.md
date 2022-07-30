# Testing GCC Port

To test the GCC Port, run the commands below

```shell
git clone -b gcc-cmp https://github.com/fedy0/shepherd.git
cd shepherd/software/firmware
chmod +x setup.sh
sudo ./setup.sh pru_iep.patch
```

0. The script above would do the following:

1. Clone this repository branch

2. Install the cross toolchain from [gnupru](https://github.com/dinuxbg/gnupru.git)

3. Install the PRU software support packages from [pssp](https://github.com/dinuxbg/pru-software-support-package.git)

4. Export PRU gcc and binutils to your env PATH

5. Patch PRU software support packages

6. Compile PRUs' firmware
