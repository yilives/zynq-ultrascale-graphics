import org.lwjgl.opengl.ARBMultitexture;
import org.lwjgl.opengl.ContextCapabilities;
import org.lwjgl.opengl.Display;
import org.lwjgl.opengl.DisplayMode;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GLContext;
import org.lwjgl.opengl.PixelFormat;

/** Exercise the real LWJGL ARB branch used by the unmodified 1.2.5 helper. */
public final class Java256ArbProbe {
    static void good(String where) {
        int error=GL11.glGetError();if(error!=0)throw new IllegalStateException(where+" GL error "+error);
    }
    public static void main(String[] args) {
        boolean created=false;int code=0;
        try {
            int units=Integer.parseInt(args[0]);
            Display.setDisplayMode(new DisplayMode(400,240));
            Display.create(new PixelFormat().withBitsPerPixel(16).withDepthBits(16).withStencilBits(0));created=true;
            ContextCapabilities caps=GLContext.getCapabilities();
            System.out.println("JAVA256_ARB_CAPS arb="+caps.GL_ARB_multitexture+" gl13="+caps.OpenGL13);
            if(!caps.GL_ARB_multitexture)throw new IllegalStateException("Real LWJGL ARB capability missing");
            if(GL11.glGetInteger(ARBMultitexture.GL_MAX_TEXTURE_UNITS_ARB)!=units)throw new IllegalStateException("TMU count mismatch");
            int[] texture=new int[units];
            for(int unit=0;unit<units;unit++) {
                ARBMultitexture.glActiveTextureARB(ARBMultitexture.GL_TEXTURE0_ARB+unit);
                ARBMultitexture.glClientActiveTextureARB(ARBMultitexture.GL_TEXTURE0_ARB+unit);
                texture[unit]=GL11.glGenTextures();GL11.glBindTexture(GL11.GL_TEXTURE_2D,texture[unit]);
                ARBMultitexture.glMultiTexCoord4fARB(ARBMultitexture.GL_TEXTURE0_ARB+unit,.125f*(unit+1),.25f,.5f,1f);
                good("valid ARB unit "+unit);
            }
            for(int unit=0;unit<units;unit++) {
                ARBMultitexture.glActiveTextureARB(ARBMultitexture.GL_TEXTURE0_ARB+unit);
                if(GL11.glGetInteger(GL11.GL_TEXTURE_BINDING_2D)!=texture[unit])throw new IllegalStateException("Texture binding alias");
                good("independent binding "+unit);
            }
            ARBMultitexture.glActiveTextureARB(ARBMultitexture.GL_TEXTURE0_ARB+units);
            if(GL11.glGetError()!=GL11.GL_INVALID_ENUM)throw new IllegalStateException("Out-of-range ARB unit accepted");
            ARBMultitexture.glActiveTextureARB(ARBMultitexture.GL_TEXTURE0_ARB);
            ARBMultitexture.glClientActiveTextureARB(ARBMultitexture.GL_TEXTURE0_ARB);good("restore unit0");
            GL11.glClearColor(0,0,0,1);GL11.glClear(GL11.GL_COLOR_BUFFER_BIT);Display.swapBuffers();
            System.out.println("JAVA256_ARB_PASS units="+units+" gl13="+caps.OpenGL13);
        } catch(Throwable failure) {failure.printStackTrace();code=1;}
        finally {if(created)Display.destroy();}
        if(code!=0)System.exit(code);
    }
}
