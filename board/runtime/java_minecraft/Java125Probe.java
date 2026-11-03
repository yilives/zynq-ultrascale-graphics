import org.lwjgl.Sys;
import org.lwjgl.opengl.Display;
import org.lwjgl.opengl.DisplayMode;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GLContext;
import org.lwjgl.opengl.PixelFormat;

/** Short, non-rendering JVM/LWJGL/GLX compatibility probe. */
public final class Java125Probe {
    public static void main(String[] args) {
        int result = 0;
        boolean created = false;
        try {
            System.out.println("JAVA125_VM " + System.getProperty("java.runtime.version")
                + " arch=" + System.getProperty("os.arch")
                + " max_heap=" + Runtime.getRuntime().maxMemory());
            System.out.println("JAVA125_AWT " + java.awt.Toolkit.getDefaultToolkit().getClass().getName());
            System.out.println("JAVA125_LWJGL " + Sys.getVersion() + " is64bit=" + Sys.is64Bit());
            if (args.length > 0 && args[0].equals("display")) {
                Display.setDisplayMode(new DisplayMode(400,240));
                Display.setTitle("RasterIX official Minecraft 1.2.5 compatibility probe");
                Display.create(new PixelFormat().withBitsPerPixel(16).withDepthBits(16).withStencilBits(0));
                created = true;
                System.out.println("JAVA125_GL_VERSION " + GL11.glGetString(GL11.GL_VERSION));
                System.out.println("JAVA125_GL_RENDERER " + GL11.glGetString(GL11.GL_RENDERER));
                System.out.println("JAVA125_GL_MAX_TEXTURE " + GL11.glGetInteger(GL11.GL_MAX_TEXTURE_SIZE));
                System.out.println("JAVA125_GL11 " + GLContext.getCapabilities().OpenGL11);
            }
            System.out.println("JAVA125_PROBE_PASS");
        } catch (Throwable error) {
            result = 2;
            System.out.println("JAVA125_PROBE_FAILED " + error);
            error.printStackTrace();
        } finally {
            if (created) Display.destroy();
        }
        System.exit(result);
    }
}
