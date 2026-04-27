pcb_x = 75.3;
pcb_y = 54.8;
pcb_z1 = 1.8;
pcb_z2 = 3.7;

hdr_x = 82.6 - pcb_x/2 - 11.2;
hdr_y = 41.2 - pcb_y/2;

hrv_x = 21.8 - pcb_x/2 - 11.2;
hrv_y = 43.8 - pcb_y/2;

include <misc_parts.scad>


module cape25()
{
    // cutouts
    union() {
        //import("shepherd_pcb_v25a.stl", convexity=100)
        // PCB + Parts (large cutout)
        translate([0,0,pcb_z1/2]) round_cuboid(x=pcb_x+0.1, y=pcb_y+0.1, z=pcb_z1+0.1,r=2.54, $fn=100);
        translate([0,0,pcb_z2/2]) round_cuboid(x=pcb_x-2*0.6, y=pcb_y-2*0.6, z=pcb_z2,r=2.54, $fn=100);
        // cutout below
        translate([0,0,-pcb_z2/2]) round_cuboid(x=pcb_x-2*0.5, y=pcb_y-2*0.5, z=pcb_z2,r=2.54, $fn=100);

        // TargetHeaders
        translate([hdr_x,+hdr_y,pcb_z1+10/2]) cube([6,23.6,10], center=true);
        translate([hdr_x,-hdr_y,pcb_z1+10/2]) cube([6,23.6,10], center=true);
        // PWR & USB
        translate([-(pcb_x-8)/2,-17,pcb_z1+10/2]) cube([8,18,10], center=true);
        translate([-pcb_x/2,-20,pcb_z2]) cube([2*8,24,15], center=true);
        // harvester
        translate([hrv_x,hrv_y,pcb_z1+10/2]) cube([6,6,10], center=true);
        // NW
        translate([-pcb_x/2 - 1.5,0,0]) cube([22,16,2*pcb_z2], center=true);

        // cutouts horizontal
        translate([0,+(4+23)/2,0]) cube([pcb_x + 10,23.2,2*pcb_z2], center=true);
        translate([0,-(4+23)/2,0]) cube([pcb_x + 10,23.2,2*pcb_z2], center=true);

        // cutouts vertical
        translate([+24.0,0,0]) cube([18,pcb_y+10,2*pcb_z2], center=true);
        translate([0.0,0,0]) cube([18,pcb_y+10,2*pcb_z2], center=true);
        translate([-24.0,0,0]) cube([18,pcb_y+10,2*pcb_z2], center=true);
    }
}

module window_honey_neg()
{
    // honey comb top
    // easy way to tune line-thickness -> d_cylinder
    intersection () {
        difference () {
            translate([0,0,pcb_z2]) round_cuboid(x=pcb_x-4.0, y=pcb_y-2.0, z=pcb_z2,r=1, $fn=100);
            // border for connectors (+2mm)
            // TargetHeaders
            translate([hdr_x,+hdr_y,pcb_z1+10/2]) round_cuboid(x=6+2,y=23.6+2,z=10,r=1);
            translate([hdr_x,-hdr_y,pcb_z1+10/2]) round_cuboid(x=6+2,y=23.6+2,z=10,r=1);
            // PWR & USB
            translate([-(pcb_x-8)/2,-17,pcb_z1+10/2]) round_cuboid(x=8+2,y=18+2,z=10,r=1);
            // harvester
            translate([hrv_x,hrv_y,pcb_z1+10/2]) round_cuboid(x=6+2,y=6+2,z=10, r=1);
            }

        for (i = [-10:1:10], j=[-10:1:10]) {
            translate([i*5.0,i*3.0 + j*6,0]) cylinder(h=25, d=5.7, $fn=6);
        }
    }
}

module cage()
{
    difference () {
        translate([0,0,pcb_z2/2]) round_cuboid3(x=pcb_x+2*1.5, y=pcb_y+2*1.5, z=pcb_z2+2*1,r=1, $fn=100);
        window_honey_neg();
        cape25();
    }
}


//cape25();
//window_honey_neg();
cage();
