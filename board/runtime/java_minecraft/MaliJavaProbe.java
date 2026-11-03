import java.nio.ByteBuffer;
import java.nio.file.*;
import org.lwjgl.BufferUtils;
import org.lwjgl.opengl.*;

/** Independent desktop-GL compatibility probe on the real Mali backend. */
public final class MaliJavaProbe {
 public static void main(String[] args) {
  int code=2;boolean created=false;
  try {
   Display.setDisplayMode(new DisplayMode(400,240));Display.setTitle("Mali Java compatibility test");
   Display.create(new PixelFormat().withBitsPerPixel(16).withDepthBits(16).withStencilBits(0));created=true;
   String renderer=GL11.glGetString(GL11.GL_RENDERER);
   System.out.println("MALI_JAVA_GL renderer="+renderer+" version="+GL11.glGetString(GL11.GL_VERSION));
   System.out.println("MALI_JAVA_CAPS gl11="+GLContext.getCapabilities().OpenGL11+" gl13="+GLContext.getCapabilities().OpenGL13+" arb="+GLContext.getCapabilities().GL_ARB_multitexture);
   if(!renderer.toLowerCase().contains("mali"))throw new IllegalStateException("Hardware Mali renderer required");
   boolean device=false;try(DirectoryStream<Path> stream=Files.newDirectoryStream(Paths.get("/proc/self/fd"))){for(Path p:stream)try{if(Files.readSymbolicLink(p).toString().equals("/dev/mali"))device=true;}catch(Exception ignored){}}
   if(!device)throw new IllegalStateException("Mali device not open");
   GL11.glViewport(0,0,400,240);GL11.glDisable(GL11.GL_DITHER);GL11.glDisable(GL11.GL_DEPTH_TEST);
   GL11.glMatrixMode(GL11.GL_PROJECTION);GL11.glLoadIdentity();GL11.glOrtho(0,400,0,240,-1,1);GL11.glMatrixMode(GL11.GL_MODELVIEW);GL11.glLoadIdentity();
   int list=GL11.glGenLists(1);if(list==0)throw new IllegalStateException("Display list allocation failed");
   GL11.glNewList(list,GL11.GL_COMPILE);GL11.glColor4f(1,0,0,1);GL11.glBegin(GL11.GL_QUADS);GL11.glVertex2f(100,100);GL11.glVertex2f(300,100);GL11.glVertex2f(300,200);GL11.glVertex2f(100,200);GL11.glEnd();GL11.glEndList();
   GL11.glClearColor(0,0,0,1);GL11.glClear(GL11.GL_COLOR_BUFFER_BIT);GL11.glCallList(list);GL11.glFinish();
   ByteBuffer pixels=BufferUtils.createByteBuffer(400*240*4);GL11.glReadPixels(0,0,400,240,GL11.GL_RGBA,GL11.GL_UNSIGNED_BYTE,pixels);
   int errors=0;for(int y=0;y<240;y++)for(int x=0;x<400;x++){int at=(y*400+x)*4;int red=(x>=100&&x<300&&y>=100&&y<200)?255:0;if((pixels.get(at)&255)!=red||(pixels.get(at+1)&255)!=0||(pixels.get(at+2)&255)!=0||(pixels.get(at+3)&255)!=255)errors++;}
   int error=GL11.glGetError();if(errors!=0||error!=0)throw new IllegalStateException("Pixels="+errors+" glError="+error);
   byte[] raw=new byte[pixels.capacity()];pixels.rewind();pixels.get(raw);Files.write(Paths.get(args[0]),raw);
   GL11.glDeleteLists(list,1);Display.update();System.out.println("MALI_JAVA_PROBE_PASS pixels=96000 display_list=1 quad=1 mali_device=1");code=0;
  } catch(Throwable e){System.out.println("MALI_JAVA_PROBE_FAILED "+e);e.printStackTrace();}
  finally{if(created)Display.destroy();}System.exit(code);
 }
}
