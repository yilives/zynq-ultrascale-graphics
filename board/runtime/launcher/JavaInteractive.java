import java.awt.Canvas;
import java.awt.Component;
import java.awt.Container;
import java.awt.Dimension;
import java.awt.EventQueue;
import java.awt.Frame;

/** Original 1.2.5 entry, physical window sizing only; no input or exit timer. */
public final class JavaInteractive {
    static void canvas(Component component) {
        if (component instanceof Canvas) {
            component.setPreferredSize(new Dimension(400, 240));
            component.setMinimumSize(new Dimension(400, 240));
        }
        if (component instanceof Container)
            for (Component child : ((Container) component).getComponents()) canvas(child);
    }
    public static void main(String[] args) throws Exception {
        Class.forName("net.minecraft.client.Minecraft").getMethod("main", String[].class).invoke(null, (Object) args);
        EventQueue.invokeAndWait(new Runnable() {
            public void run() {
                for (Frame frame : Frame.getFrames())
                    if (frame.isDisplayable() && frame.getTitle().toLowerCase().contains("minecraft")) {
                        frame.setResizable(false);
                        canvas(frame);
                        frame.pack();
                        frame.getGraphicsConfiguration().getDevice().setFullScreenWindow(frame);
                        System.out.println("LAUNCHER_JAVA_WINDOW " + frame.getWidth() + "x" + frame.getHeight());
                    }
            }
        });
    }
}
