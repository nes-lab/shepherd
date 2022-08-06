# Installing Prerequisites

run the commands below

```shell
git clone -b gcc-port https://github.com/fedy0/shepherd.git
cd shepherd/software/firmware
chmod +x *.sh
./setup.sh
source ~/.bashrc
```

The commands above do the following:

1. Clone this repository branch

2. Install the cross toolchain from [gnupru](https://github.com/dinuxbg/gnupru.git)

3. Install the PRU software support packages from [pssp](https://github.com/dinuxbg/pru-software-support-package.git)

4. Export toolchain-paths to users environmental variables & reload .bashrc

# Compiling GCC Port

- compilation and cleaning can and should be done without sudo
- installation needs sudo as it copies the firmware to system-

```shell
make 
sudo make install
make clean
```
