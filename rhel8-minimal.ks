#version=RHEL8
#mount the ISO over iLO virtual media
install
cdrom
lang en_US.UTF-8
keyboard us
network --bootproto=manual --device=enp1s0 --onboot=on --ip=192.168.1.50 --netmask=255.255.255.0 --gateway=192.168.1.1
rootpw --plaintext Nokia123
firewall --enabled --service=ssh
timezone Asia/Kolkata --isUtc
bootloader --location=mbr
clearpart --all --initlabel
part / --size=102400 --fstype="xfs" --grow --asprimary
part /home --size=1 --fstype="xfs" --grow
part swap --size=8192
%packages
@core
%end
