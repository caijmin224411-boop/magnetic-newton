import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class DiskMagnetForceTable {
    static final double MU0 = 4.0 * Math.PI * 1e-7;

    static class Patch {
        final double u;
        final double v;
        final double area;

        Patch(double u, double v, double area) {
            this.u = u;
            this.v = v;
            this.area = area;
        }
    }

    static class Surface {
        final double x;
        final double sign;

        Surface(double x, double sign) {
            this.x = x;
            this.sign = sign;
        }
    }

    static List<Patch> diskPatches(double radius, int radialSteps, int angularSteps) {
        List<Patch> patches = new ArrayList<>();
        for (int ir = 0; ir < radialSteps; ir++) {
            double r0 = radius * ir / radialSteps;
            double r1 = radius * (ir + 1) / radialSteps;
            double rm = 0.5 * (r0 + r1);
            double ringArea = Math.PI * (r1 * r1 - r0 * r0);
            int ntheta = Math.max(8, (int)Math.round(angularSteps * Math.max(rm / radius, 0.18)));
            for (int it = 0; it < ntheta; it++) {
                double phi = 2.0 * Math.PI * (it + 0.5) / ntheta;
                patches.add(new Patch(rm * Math.cos(phi), rm * Math.sin(phi), ringArea / ntheta));
            }
        }
        return patches;
    }

    static double[] forceOnRightMagnet(
            List<Patch> disk,
            double gap,
            double lateralOffset,
            double radius,
            double thickness,
            double br
    ) {
        double sigma = br / MU0;
        double centerDistance = gap + thickness;
        double coeff = MU0 / (4.0 * Math.PI);

        // Magnet axis is x. Facing surfaces are same-pole and repel.
        Surface[] leftMagnet = new Surface[] {
            new Surface(-0.5 * thickness, -1.0),
            new Surface(+0.5 * thickness, +1.0)
        };
        Surface[] rightMagnet = new Surface[] {
            new Surface(centerDistance - 0.5 * thickness, +1.0),
            new Surface(centerDistance + 0.5 * thickness, -1.0)
        };

        double fxTotal = 0.0;
        double fyTotal = 0.0;

        for (Surface s1 : leftMagnet) {
            for (Surface s2 : rightMagnet) {
                for (Patch p1 : disk) {
                    double q1 = s1.sign * sigma * p1.area;
                    double x1 = s1.x;
                    double y1 = p1.u;
                    double z1 = p1.v;
                    for (Patch p2 : disk) {
                        double q2 = s2.sign * sigma * p2.area;
                        double dx = s2.x - x1;
                        double dy = (p2.u + lateralOffset) - y1;
                        double dz = p2.v - z1;
                        double r2 = dx * dx + dy * dy + dz * dz;
                        double r = Math.sqrt(r2);
                        double f = coeff * q1 * q2 / (r2 * r);
                        fxTotal += f * dx;
                        fyTotal += f * dy;
                    }
                }
            }
        }
        return new double[] {fxTotal, fyTotal};
    }

    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.US);

        double radius = argDouble(args, 0, 0.0115);
        double thickness = argDouble(args, 1, 0.0040);
        double br = argDouble(args, 2, 1.45);
        double minGap = argDouble(args, 3, 0.0008);
        double maxGap = argDouble(args, 4, 0.0400);
        int gapCount = argInt(args, 5, 64);
        double maxOffset = argDouble(args, 6, 0.0400);
        int offsetCount = argInt(args, 7, 25);
        int radialSteps = argInt(args, 8, 7);
        int angularSteps = argInt(args, 9, 36);
        String output = args.length > 10 ? args[10] : "force_table_n52_disk_2d.csv";

        List<Patch> disk = diskPatches(radius, radialSteps, angularSteps);
        File outFile = new File(output);
        try (PrintWriter out = new PrintWriter(outFile, "UTF-8")) {
            out.println("gap_m,offset_m,force_axial_N,force_lateral_N");
            for (int ig = 0; ig < gapCount; ig++) {
                double s = (double)ig / (gapCount - 1);
                double gap = minGap * Math.pow(maxGap / minGap, s);
                for (int io = 0; io < offsetCount; io++) {
                    double offset = maxOffset * io / (offsetCount - 1);
                    double[] f = forceOnRightMagnet(disk, gap, offset, radius, thickness, br);
                    out.printf(Locale.US, "%.10g,%.10g,%.10g,%.10g%n", gap, offset, f[0], f[1]);
                }
            }
        }

        System.out.println("Wrote " + outFile.getAbsolutePath());
        System.out.println("Effective Br_T=" + br + ", radius_m=" + radius + ", thickness_m=" + thickness);
        System.out.println("patch_count_per_surface=" + disk.size());
    }

    static double argDouble(String[] args, int idx, double defaultValue) {
        return args.length > idx ? Double.parseDouble(args[idx]) : defaultValue;
    }

    static int argInt(String[] args, int idx, int defaultValue) {
        return args.length > idx ? Integer.parseInt(args[idx]) : defaultValue;
    }
}
