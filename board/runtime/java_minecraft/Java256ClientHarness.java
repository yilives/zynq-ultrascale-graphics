import java.awt.Canvas;
import java.awt.Component;
import java.awt.Container;
import java.awt.Dimension;
import java.awt.EventQueue;
import java.awt.Frame;
import java.awt.Robot;
import java.awt.event.InputEvent;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Timer;
import java.util.TimerTask;
import org.lwjgl.opengl.Display;

/** Keep official game code intact; constrain its window to the physical renderer. */
public final class Java256ClientHarness {
    static Object gameInstance() throws Exception {
        Class<?> mc=Class.forName("net.minecraft.client.Minecraft");
        for(Field field:mc.getDeclaredFields()) if(Modifier.isStatic(field.getModifiers())&&field.getType()==mc) {
            field.setAccessible(true);Object game=field.get(null);if(game!=null)return game;
        }
        throw new IllegalStateException("No Minecraft instance");
    }
    static void dimensions(Component c) {
        if(c instanceof Canvas) System.out.println("JAVA256_CANVAS "+c.getWidth()+"x"+c.getHeight());
        if(c instanceof Container) for(Component child:((Container)c).getComponents()) dimensions(child);
    }
    static void diagnose() {
        try {
            for(Frame f:Frame.getFrames()) if(f.isDisplayable()) dimensions(f);
            System.out.println("JAVA256_DISPLAY "+Display.getWidth()+"x"+Display.getHeight());
            Class<?> mc=Class.forName("net.minecraft.client.Minecraft");
            for(Field field:mc.getDeclaredFields()) if(Modifier.isStatic(field.getModifiers())&&field.getType()==mc) {
                field.setAccessible(true);Object game=field.get(null);if(game==null) continue;
                System.out.println("JAVA256_GAME "+mc.getField("d").getInt(game)+"x"+mc.getField("e").getInt(game));
                Object screen=mc.getField("s").get(game);
                if(screen!=null) System.out.println("JAVA256_GUI "+screen.getClass().getName()+" "+screen.getClass().getField("q").getInt(screen)+"x"+screen.getClass().getField("r").getInt(screen));
            }
        } catch(Exception failure) { System.out.println("JAVA256_DIMENSIONS_FAILED "+failure); }
    }
    static final class SizeProbe extends TimerTask {
        public void run() { EventQueue.invokeLater(Java256ClientHarness::diagnose); }
    }
    static final class MenuClick extends TimerTask {
        public void run() {
            try {
                Object game=gameInstance();Class<?> mc=game.getClass();
                Object screen=mc.getField("s").get(game);
                if(screen==null||!screen.getClass().getName().equals("xt")||
                   mc.getField("d").getInt(game)!=400||mc.getField("e").getInt(game)!=240||
                   Display.getWidth()!=400||Display.getHeight()!=240)
                    throw new IllegalStateException("Main menu and physical dimensions required");
                Robot input=new Robot();input.setAutoDelay(100);
                input.mouseMove(200,118);input.mousePress(InputEvent.BUTTON1_DOWN_MASK);
                input.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
                System.out.println("JAVA256_INPUT_SINGLEPLAYER_CLICK 200,118");
            } catch(Exception failure) {System.out.println("JAVA256_INPUT_FAILED "+failure);}
        }
    }
    static void canvasSize(Component c) {
        if(c instanceof Canvas) {
            c.setPreferredSize(new Dimension(400,240));
            c.setMinimumSize(new Dimension(400,240));
        }
        if(c instanceof Container) for(Component child:((Container)c).getComponents()) canvasSize(child);
    }
    public static void main(String[] args) throws Exception {
        Java125ClientHarness.main(args);
        EventQueue.invokeAndWait(new Runnable() {
            public void run() {
                for(Frame f:Frame.getFrames()) if(f.isDisplayable()&&f.getTitle().toLowerCase().contains("minecraft")) {
                    f.setResizable(false);canvasSize(f);f.pack();
                    // Match the physical framebuffer: window-manager decorations/workarea
                    // otherwise shrink the Canvas (observed 400x174 for a 400x240 request).
                    java.awt.GraphicsDevice screen=f.getGraphicsConfiguration().getDevice();
                    System.out.println("JAVA256_FULLSCREEN supported="+screen.isFullScreenSupported()+" bounds="+screen.getDefaultConfiguration().getBounds());
                    screen.setFullScreenWindow(f);
                    System.out.println("JAVA256_CLIENT_WINDOW "+f.getWidth()+"x"+f.getHeight());
                }
            }
        });
        new Timer("java256-size-probe",true).schedule(new SizeProbe(),8000L,8000L);
        if("singleplayer".equals(System.getenv("RIX_JAVA_MENU_CLICK")))
            new Timer("java256-menu-input",true).schedule(new MenuClick(),12000L);
    }
}
