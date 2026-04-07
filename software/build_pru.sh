# dev-script for faster rebuilding (compared to ansible)
CAPE_HW_VER=24
cd /opt/shepherd/software/firmware/pru0-shepherd-fw/
# EMU
sudo make clean
make TYPE=EMU CAPE_HW_VER=$CAPE_HW_VER
sudo make install TYPE=EMU CAPE_HW_VER=$CAPE_HW_VER
# HRV
sudo make clean
make TYPE=HRV CAPE_HW_VER=$CAPE_HW_VER
sudo make install TYPE=HRV CAPE_HW_VER=$CAPE_HW_VER
#
cd /opt/shepherd/software/firmware/pru1-shepherd-fw/
# GPIO
sudo make clean
make CAPE_HW_VER=$CAPE_HW_VER
sudo make install CAPE_HW_VER=$CAPE_HW_VER
#
cd /opt/shepherd/software/firmware/pru0-programmer/
# PRG SWD
sudo make clean
make TYPE=SWD CAPE_HW_VER=$CAPE_HW_VER
sudo make install TYPE=SWD CAPE_HW_VER=$CAPE_HW_VER
# PROG SBW
sudo make clean
make TYPE=SBW CAPE_HW_VER=$CAPE_HW_VER
sudo make install TYPE=SBW CAPE_HW_VER=$CAPE_HW_VER
#
cd /opt/shepherd/software/
