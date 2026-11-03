import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import javax.imageio.ImageIO;
import org.lwjgl.BufferUtils;
import org.lwjgl.opengl.Display;
import org.lwjgl.opengl.DisplayMode;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.PixelFormat;

/** Validate the exact original PNG and RGBA path that initially blocked 1.2.5. */
public final class Java256MojangProbe {
    static void check(String where) {Java256TextureProbe.error(where);}
    static int channel(int value) {return ((value>>4)*17)>>3;}
    public static void main(String[] args) {
        boolean created=false;int code=0;
        try {
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try(InputStream in=Java256MojangProbe.class.getResourceAsStream("/title/mojang.png")) {
                if(in==null)throw new IllegalStateException("Official PNG absent");
                byte[] block=new byte[4096];int count;
                while((count=in.read(block))!=-1)bytes.write(block,0,count);
            }
            StringBuilder hash=new StringBuilder();
            for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes.toByteArray()))hash.append(String.format("%02x",b&255));
            BufferedImage image=ImageIO.read(new ByteArrayInputStream(bytes.toByteArray()));
            if(image.getWidth()!=256||image.getHeight()!=256)throw new IllegalStateException("Original PNG must be 256 square");
            Display.setDisplayMode(new DisplayMode(400,240));Display.setTitle("Original Mojang RGBA256 validation");
            Display.create(new PixelFormat().withBitsPerPixel(16).withDepthBits(16).withStencilBits(0));created=true;
            if(GL11.glGetInteger(GL11.GL_MAX_TEXTURE_SIZE)!=256)throw new IllegalStateException("Wrong hardware profile");
            GL11.glReadBuffer(GL11.GL_FRONT);GL11.glViewport(0,0,400,240);
            GL11.glMatrixMode(GL11.GL_PROJECTION);GL11.glLoadIdentity();GL11.glOrtho(0,400,0,240,-1,1);
            GL11.glMatrixMode(GL11.GL_MODELVIEW);GL11.glLoadIdentity();
            GL11.glDisable(GL11.GL_BLEND);GL11.glDisable(GL11.GL_ALPHA_TEST);GL11.glDisable(GL11.GL_DEPTH_TEST);
            GL11.glDisable(GL11.GL_LIGHTING);GL11.glDisable(GL11.GL_FOG);GL11.glDisable(GL11.GL_CULL_FACE);
            GL11.glEnable(GL11.GL_TEXTURE_2D);GL11.glColor4f(1,1,1,1);
            int texture=GL11.glGenTextures();GL11.glBindTexture(GL11.GL_TEXTURE_2D,texture);
            GL11.glTexParameteri(GL11.GL_TEXTURE_2D,GL11.GL_TEXTURE_MIN_FILTER,GL11.GL_NEAREST);
            GL11.glTexParameteri(GL11.GL_TEXTURE_2D,GL11.GL_TEXTURE_MAG_FILTER,GL11.GL_NEAREST);
            GL11.glTexEnvi(GL11.GL_TEXTURE_ENV,GL11.GL_TEXTURE_ENV_MODE,GL11.GL_REPLACE);
            ByteBuffer rgba=BufferUtils.createByteBuffer(256*256*4);
            for(int y=0;y<256;y++)for(int x=0;x<256;x++) {
                int pixel=image.getRGB(x,y);
                rgba.put((byte)(pixel>>16)).put((byte)(pixel>>8)).put((byte)pixel).put((byte)(pixel>>>24));
            }
            rgba.flip();GL11.glTexImage2D(GL11.GL_TEXTURE_2D,0,GL11.GL_RGBA,256,256,0,GL11.GL_RGBA,GL11.GL_UNSIGNED_BYTE,rgba);
            check("original 256 RGBA PNG upload");
            byte[] output=new byte[256*256*3];int bad=0;
            for(int part=0;part<2;part++) {
                float t0=part*.5f,t1=t0+.5f;
                GL11.glClearColor(0,0,0,1);GL11.glClear(GL11.GL_COLOR_BUFFER_BIT);
                GL11.glBegin(GL11.GL_QUADS);
                GL11.glTexCoord2f(0,t0);GL11.glVertex2f(0,0);
                GL11.glTexCoord2f(1,t0);GL11.glVertex2f(256,0);
                GL11.glTexCoord2f(1,t1);GL11.glVertex2f(256,128);
                GL11.glTexCoord2f(0,t1);GL11.glVertex2f(0,128);GL11.glEnd();
                Display.swapBuffers();
                ByteBuffer read=BufferUtils.createByteBuffer(256*128*4);
                GL11.glReadPixels(0,0,256,128,GL11.GL_RGBA,GL11.GL_UNSIGNED_BYTE,read);check("RGBA PNG front readback");
                for(int y=0;y<128;y++)for(int x=0;x<256;x++) {
                    int i=y*256+x,at=i*4,r=read.get(at)&255,g=read.get(at+1)&255,b=read.get(at+2)&255;
                    int source=image.getRGB(x,part*128+y);
                    int expected=(channel((source>>16)&255)<<11)|(channel((source>>8)&255)<<6)|channel(source&255);
                    int observed=((r>>3)<<11)|((g>>2)<<5)|(b>>3);
                    if((observed&0xffdf)!=expected) {
                        if(bad<8)System.out.println("MOJANG_PIXEL_MISMATCH "+x+","+y+" got="+observed+" expected="+expected);
                        bad++;
                    }
                    int dest=((part*128+y)*256+x)*3;
                    output[dest]=(byte)r;output[dest+1]=(byte)g;output[dest+2]=(byte)b;
                }
            }
            try(FileOutputStream f=new FileOutputStream(args[0])) {f.write("P6\n256 256\n255\n".getBytes("US-ASCII"));f.write(output);}
            System.out.println("JAVA256_MOJANG_CHECK pixels=65536 mismatches="+bad+" rgba4444=1 source_png_sha256="+hash+" resampled=0");
            if(bad!=0)throw new IllegalStateException("Original RGBA texture pixels differ");
            GL11.glDeleteTextures(texture);System.out.println("JAVA256_MOJANG_PASS");
        } catch(Throwable failure) {code=2;failure.printStackTrace();}
        finally {if(created)Display.destroy();}
        System.exit(code);
    }
}
