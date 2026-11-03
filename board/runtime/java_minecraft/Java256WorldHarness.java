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
public final class Java256WorldHarness {
    static final Timer TIMER=new Timer("java-world-input",true);
    static int phase=0;static long began=0;static Robot input;
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
        Process process=new ProcessBuilder("plgpuctl","status").redirectErrorStream(true).start();
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();InputStream in=process.getInputStream();byte[] data=new byte[4096];
        for(int count;(count=in.read(data))>=0;)bytes.write(data,0,count);
        if(process.waitFor()!=0)throw new IllegalStateException("GPU status failed");return new String(bytes.toByteArray(),"UTF-8").trim();
    }
    static void step() throws Exception {
        if(phase>=7)return;
        Object game=Java256ClientHarness.gameInstance();Class<?> mc=game.getClass();Object screen=mc.getField("s").get(game);
        if(Display.getWidth()!=400||Display.getHeight()!=240)throw new IllegalStateException("Physical dimensions changed");
        String gui=screen==null?"none":screen.getClass().getName();
        if(phase==0&&gui.equals("xt")&&click(screen,"Singleplayer",false)) {
            System.out.println("JAVA256_INPUT_SINGLEPLAYER_CLICK original_button");phase=1;
        } else if(phase==1&&gui.equals("mw")&&click(screen,"Create New World",false)) {
            System.out.println("JAVA256_GUI mw 400x240");phase=2;
        } else if(phase==2&&button(screen,"More World Options",true)!=null) {
            input.mouseMove(200,70);input.mousePress(InputEvent.BUTTON1_DOWN_MASK);input.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
            input.keyPress(KeyEvent.VK_CONTROL);input.keyPress(KeyEvent.VK_A);input.keyRelease(KeyEvent.VK_A);input.keyRelease(KeyEvent.VK_CONTROL);
            String name=System.getProperty("rix.world.name","rixjava-r22");
            if(!name.matches("[a-z0-9-]{1,32}"))throw new IllegalStateException("Invalid probe world name");
            for(char ch:name.toCharArray()){int key=KeyEvent.getExtendedKeyCodeForChar(ch);input.keyPress(key);input.keyRelease(key);}
            if(click(screen,"More World Options",true))phase=3;
        } else if(phase==3&&button(screen,"World Type:",true)!=null) {
            Object type=button(screen,"World Type:",true);String text=(String)Class.forName("abp").getField("e").get(type);
            if(text.contains("Superflat")){phase=4;System.out.println("JAVA_WORLD_TYPE Superflat");}
            else click(screen,"World Type:",true);
        } else if(phase==4&&click(screen,"Create New World",false)) {
            phase=5;System.out.println("JAVA_WORLD_CREATE_REQUEST original_gui=1");
        } else if(phase==5&&screen==null&&mc.getField("f").get(game)!=null&&mc.getField("h").get(game)!=null) {
            phase=6;began=System.nanoTime();System.out.println("JAVA_WORLD_ACTIVE world=1 player=1 gui=none");
            System.out.println("JAVA_WORLD_STATUS_START "+gpuStatus());
            input.keyPress(KeyEvent.VK_W);TIMER.schedule(new TimerTask(){public void run(){input.keyRelease(KeyEvent.VK_W);}},2000);
        } else if(phase==6&&System.nanoTime()-began>=10000000000L) {
            if(screen!=null||mc.getField("f").get(game)==null||mc.getField("h").get(game)==null)throw new IllegalStateException("World left during measurement");
            System.out.println("JAVA_WORLD_STATUS_END "+gpuStatus());System.out.println("JAVA_WORLD_MEASURE elapsed_ns="+(System.nanoTime()-began));phase=7;
            System.out.println("JAVA_WORLD_ACTIVE_INTERVAL_PASS");
            TIMER.schedule(new TimerTask(){public void run(){closeNormally();}},8000);
        }
    }
    public static void main(String[] args) throws Exception {
        TIMER.schedule(new TimerTask(){public void run(){closeNormally();}},90000);
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
