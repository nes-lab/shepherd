
// Classic Wall Generator needs +0.15, Arachne more like +0.30
plug_dim = [1.6 + 0.25, 17.3 + 0.30, 6 + 0.2];
plug_distance = 9;
plug_count = 10;
d_clamp = 20;
s_clamp = 0.20; // narrowing on both sides

$fn=48;

module round_cuboid(x,y,z,r)
{
    cube([x,y-2*r,z],center=true);
    cube([x-2*r,y,z],center=true);
    cube([x-2*r,y-2*r,z],center=true);

    translate([+x/2-r,+y/2-r,0]) cylinder(r=r,h=z,center=true);
    translate([+x/2-r,-y/2+r,0]) cylinder(r=r,h=z,center=true);
    translate([-x/2+r,+y/2-r,0]) cylinder(r=r,h=z,center=true);
    translate([-x/2+r,-y/2+r,0]) cylinder(r=r,h=z,center=true);
}


difference () {
    case_x = 8 + plug_count * plug_distance;
    case_y = 8 + plug_dim[1];
    case_z = plug_dim[2] - 0.1;
    round_cuboid(case_x, case_y, case_z, 6);
    translate([0,0,0.99]) round_cuboid(case_x-8, case_y-12, case_z-1, 3);
    plug_range = (plug_count - 1) / 2;
    narrowing_x = (d_clamp/2 + plug_dim[0]/2 - s_clamp);
    narrowing_y = (plug_dim[1] - .1) / 2;
    clamp_xyz = [plug_distance-1.5,1,plug_dim[2]];
    slot_xyz = [plug_distance-2.0, case_y-12.1, case_z+1];
    for (i = [-plug_range:1:plug_range]) {
        translate([i*plug_distance,0,0])     difference() {
            // usb-plug
            cube(plug_dim, center=true);
            // a narrow clamping piece on both sides
            translate([+narrowing_x,+narrowing_y,0]) sphere(d=d_clamp,$fn=120);
            translate([+narrowing_x,-narrowing_y,0]) sphere(d=d_clamp,$fn=120);
            //translate([-narrowing_x,+narrowing_y,0]) sphere(d=d_clamp,$fn=120);
            //translate([-narrowing_x,-narrowing_y,0]) sphere(d=d_clamp,$fn=120);

        }
        // a slot for some spring clamping
        translate([i*plug_distance,+plug_dim[1]/2 + 1.5,0]) cube(clamp_xyz, center=true);
        translate([i*plug_distance,-plug_dim[1]/2 - 1.5,0]) cube(clamp_xyz, center=true);
        translate([i*plug_distance,0,0]) cube(slot_xyz, center=true);
        }
    }

/*
difference () {
    round_cuboid(12, 22, 5.5, 3);
    difference() {
        // usb-plug and a narrow clamping piece on both sides
        cube(plug_dim, center=true);
        translate([+(d_clamp/2 + plug_dim[0]/2 - s_clamp),0,0]) sphere(d=d_clamp,$fn=160);
        translate([-(d_clamp/2 + plug_dim[0]/2 - s_clamp),0,0]) sphere(d=d_clamp,$fn=160);
    }
}
*/
