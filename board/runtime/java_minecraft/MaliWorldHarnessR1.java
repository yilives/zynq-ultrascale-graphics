import java.awt.EventQueue;
import java.awt.Frame;
import java.awt.GraphicsDevice;
import java.awt.Robot;
import java.awt.event.InputEvent;
import java.awt.event.KeyEvent;
import java.awt.event.WindowEvent;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.util.List;
import java.util.Timer;
import java.util.TimerTask;
import org.lwjgl.opengl.Display;

/** Operate original GUI buttons with X11 keyboard/mouse; do not replace game logic. */
public final class MaliWorldHarnessR1 {
    static final Timer TIMER=new Timer("java-world-input",true);
    static int selectY=0;static int phase=0;static long began=0;static long launchRequested=0;static Robot input;
    static void closeNormally() {
        if(input!=null)input.keyRelease(KeyEvent.VK_W);
        EventQueue.invokeLater(new Runnable(){public void run(){for(Frame frame:Frame.getFrames())
            if(frame.isDisplayable()&&frame.getTitle().toLowerCase().contains("minecraft")) {
                System.out.println("JAVA125_NORMAL_CLOSE_REQUEST "+frame.getTitle());
                frame.dispatchEvent(new WindowEvent(frame,WindowEvent.WINDOW_CLOSING));
            }}});
    }
    static Object button(Object screen,String label,boolean prefix) throws Exception {
        if(screen==null)return null;
        Field list=Class.forName("vp").getDeclaredField("s");list.setAccessible(true);
        for(Object b:((List<?>)list.get(screen)).toArray()) {
            Class<?> type=Class.forName("abp");String text=(String)type.getField("e").get(b);
            if((prefix?text.startsWith(label):text.equals(label))&&type.getField("h").getBoolean(b)&&type.getField("i").getBoolean(b))return b;
        }
        return null;
    }
    static boolean click(Object screen,String label,boolean prefix) throws Exception {
        Object b=button(screen,label,prefix);if(b==null)return false;Class<?> type=Class.forName("abp");
        Field width=type.getDeclaredField("a"),height=type.getDeclaredField("b");width.setAccessible(true);height.setAccessible(true);
        int x=type.getField("c").getInt(b)+width.getInt(b)/2,y=type.getField("d").getInt(b)+height.getInt(b)/2;
        input.mouseMove(x,y);input.mousePress(InputEvent.BUTTON1_DOWN_MASK);input.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        System.out.println("JAVA_WORLD_CLICK "+type.getField("e").get(b)+" "+x+","+y);return true;
    }
    static String gpuStatus() throws Exception {
        java.nio.file.Path path=java.nio.file.Paths.get(System.getProperty("rix.mali.stats"));
        for(int retry=0;retry<100;retry++) {
            byte[] raw=java.nio.file.Files.readAllBytes(path);
            if(raw.length!=128)throw new IllegalStateException("Counter size");
            java.nio.ByteBuffer data=java.nio.ByteBuffer.wrap(raw).order(java.nio.ByteOrder.LITTLE_ENDIAN);
            long magic=data.getLong(0),seq=data.getLong(8),count=data.getLong(16),ns=data.getLong(24),swap=data.getLong(32);
            byte[] verify=java.nio.file.Files.readAllBytes(path);
            long second=java.nio.ByteBuffer.wrap(verify).order(java.nio.ByteOrder.LITTLE_ENDIAN).getLong(8);
            if(magic==0x5249584d414c4931L&&seq==second&&(seq&1)==0&&count>0) return "{\"completed\":"+count+",\"monotonic_ns\":"+ns+",\"swap_ns\":"+swap+"}";
            Thread.sleep(1);
        }
        throw new IllegalStateException("No stable completed swap counter");
    }
    static void requestCapture() throws Exception {
        java.nio.ByteBuffer request=java.nio.ByteBuffer.allocate(8).order(java.nio.ByteOrder.LITTLE_ENDIAN).putLong(1);request.flip();
        try(java.nio.channels.FileChannel file=java.nio.channels.FileChannel.open(java.nio.file.Paths.get(System.getProperty("rix.mali.stats")),java.nio.file.StandardOpenOption.WRITE)){file.position(64);while(request.hasRemaining())file.write(request);}
    }
    static void step() throws Exception {
        if(phase>=7)return;
        if(phase==6) {
            Object current=Java256ClientHarness.gameInstance();
            if(current.getClass().getField("s").get(current)!=null)throw new IllegalStateException("GUI entered during measurement");
        }
        Object game=Java256ClientHarness.gameInstance();Class<?> mc=game.getClass();Object screen=mc.getField("s").get(game);
        if(Display.getWidth()!=400||Display.getHeight()!=240)throw new IllegalStateException("Physical dimensions changed");
        String gui=screen==null?"none":screen.getClass().getName();
        if(phase==0&&gui.equals("xt")&&click(screen,"Singleplayer",false)) {
            System.out.println("JAVA256_INPUT_SINGLEPLAYER_CLICK original_button");phase=1;
        } else if(phase==1&&gui.equals("mw")) {
            Class<?> type=screen.getClass();Field list=type.getDeclaredField("f");list.setAccessible(true);
            java.lang.reflect.Method folder=type.getDeclaredMethod("a",int.class);folder.setAccessible(true);
            List<?> worlds=(List<?>)list.get(screen);int selected=-1;
            System.out.println("JAVA256_GUI mw 400x240");
            for(int i=0;i<worlds.size();i++)if(System.getProperty("rix.world.name").equals(folder.invoke(screen,i)))selected=i;
            if(selected<0||selected>2)throw new IllegalStateException("Probe world not visible");
            selectY=32+selected*36+18;input.mouseMove(200,selectY);input.mousePress(InputEvent.BUTTON1_DOWN_MASK);input.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
            System.out.println("JAVA_WORLD_SELECT_SAVE "+System.getProperty("rix.world.name")+" index="+selected);phase=2;
        } else if(phase==2&&screen!=null&&screen.getClass().getName().equals("mw")) {
            Class<?> type=screen.getClass();Field selectedField=type.getDeclaredField("e");selectedField.setAccessible(true);
            int selected=selectedField.getInt(screen);java.lang.reflect.Method folder=type.getDeclaredMethod("a",int.class);folder.setAccessible(true);
            Field list=type.getDeclaredField("f");list.setAccessible(true);List<?> worlds=(List<?>)list.get(screen);int wanted=-1;
            for(int i=0;i<worlds.size();i++)if(System.getProperty("rix.world.name").equals(folder.invoke(screen,i)))wanted=i;
            if(wanted<0)throw new IllegalStateException("Target save missing");
            if(selected!=wanted){
                selectY+=selected<0?12:(wanted-selected)*36;
                if(selectY<36||selectY>170)throw new IllegalStateException("Target slot outside safe list area");
                input.mouseMove(200,selectY);input.mousePress(InputEvent.BUTTON1_DOWN_MASK);input.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
                System.out.println("JAVA_WORLD_SELECTION_RETRY selected="+selected+" wanted="+wanted);return;
            }
            System.out.println("JAVA_WORLD_SELECTED_FOLDER "+folder.invoke(screen,selected));
            if(click(screen,"Play Selected World",false)){phase=5;launchRequested=System.nanoTime();System.out.println("JAVA_WORLD_REUSE_REQUEST original_gui=1");}
        } else if(phase==5&&gui.equals("mw")&&System.nanoTime()-launchRequested>=3000000000L) {
            phase=2;System.out.println("JAVA_WORLD_REUSE_RETRY original_gui=1");
        } else if(phase==5&&screen==null&&mc.getField("f").get(game)!=null&&mc.getField("h").get(game)!=null) {
            if(began==0){
                Object settings=mc.getField("A").get(game);
                int view=settings.getClass().getField("e").getInt(settings);
                if(view!=Integer.getInteger("rix.mali.viewDistance"))throw new IllegalStateException("Wrong effective viewDistance "+view);
                System.out.println("MALI_RUNTIME_SETTINGS viewDistance="+view+" fpsLimit="+settings.getClass().getField("i").getInt(settings));
                began=System.nanoTime();System.out.println("JAVA_WORLD_WARMUP stationary_seconds=60");}
            if(System.nanoTime()-began>=60000000000L){
                phase=6;began=System.nanoTime();System.out.println("JAVA_WORLD_ACTIVE world=1 player=1 gui=none");
                System.out.println("JAVA_WORLD_MONO_START "+began);
                System.out.println("JAVA_WORLD_STATUS_START "+gpuStatus());
            }
        } else if(phase==6&&System.nanoTime()-began>=30000000000L) {
            if(screen!=null||mc.getField("f").get(game)==null||mc.getField("h").get(game)==null)throw new IllegalStateException("World left during measurement");
            System.out.println("JAVA_WORLD_STATUS_END "+gpuStatus());System.out.println("JAVA_WORLD_MONO_END "+System.nanoTime());System.out.println("JAVA_WORLD_MEASURE elapsed_ns="+(System.nanoTime()-began));phase=7;
            requestCapture();System.out.println("JAVA_WORLD_ACTIVE_INTERVAL_PASS");
            TIMER.schedule(new TimerTask(){public void run(){closeNormally();}},8000);
        }
    }
    public static void main(String[] args) throws Exception {
        TIMER.schedule(new TimerTask(){public void run(){closeNormally();}},180000);
        Class.forName("net.minecraft.client.Minecraft").getMethod("main",String[].class).invoke(null,(Object)args);
        EventQueue.invokeAndWait(new Runnable(){public void run(){for(Frame f:Frame.getFrames())
            if(f.isDisplayable()&&f.getTitle().toLowerCase().contains("minecraft")) {
                f.setResizable(false);Java256ClientHarness.canvasSize(f);f.pack();GraphicsDevice device=f.getGraphicsConfiguration().getDevice();device.setFullScreenWindow(f);
                System.out.println("JAVA256_CLIENT_WINDOW "+f.getWidth()+"x"+f.getHeight());
            }}});
        input=new Robot();input.setAutoDelay(60);
        TIMER.scheduleAtFixedRate(new TimerTask(){public void run(){try{step();}catch(Exception failure){System.out.println("JAVA_WORLD_INPUT_FAILED phase="+phase+" "+failure);}}},3000,1000);
    }
}
