import java.awt.EventQueue;
import java.awt.Frame;
import java.awt.event.WindowEvent;
import java.lang.reflect.Method;
import java.util.Timer;
import java.util.TimerTask;

/** Invoke the unchanged official entry, then request its own normal window close. */
public final class Java125ClientHarness {
    public static void main(final String[] args) throws Exception {
        final int seconds = Integer.getInteger("rix.java125.closeSeconds", 12);
        if (seconds < 10 || seconds > 30) throw new IllegalArgumentException("closeSeconds outside 10..30");
        new Timer("java125-normal-close", true).schedule(new TimerTask() {
            public void run() {
                EventQueue.invokeLater(new Runnable() {
                    public void run() {
                        for (Frame frame : Frame.getFrames()) {
                            if (frame.isDisplayable() && frame.getTitle().toLowerCase().contains("minecraft")) {
                                System.out.println("JAVA125_NORMAL_CLOSE_REQUEST " + frame.getTitle());
                                frame.dispatchEvent(new WindowEvent(frame, WindowEvent.WINDOW_CLOSING));
                            }
                        }
                    }
                });
            }
        }, seconds * 1000L);
        Method main = Class.forName("net.minecraft.client.Minecraft").getMethod("main", String[].class);
        main.invoke(null, (Object) args);
    }
}
