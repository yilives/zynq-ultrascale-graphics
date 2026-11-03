import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import org.lwjgl.BufferUtils;
import org.lwjgl.opengl.Display;
import org.lwjgl.opengl.DisplayMode;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.PixelFormat;

/** Preserve every 256x256 source texel; verify two 1:1 strips on real RasterIX. */
public final class Java256TextureProbe {
    static int texel(int index,int epoch) {
        return epoch==0?index:((index<<1)|(index>>>15))&65535;
    }
    static ByteBuffer pattern(int epoch) {
        ByteBuffer buffer=BufferUtils.createByteBuffer(256*256*3);
        for(int i=0;i<65536;i++) {
            int v=texel(i,epoch);
            buffer.put((byte)(((v>>11)&31)<<3)).put((byte)(((v>>5)&63)<<2)).put((byte)((v&31)<<3));
        }
        buffer.flip();return buffer;
    }
    static void error(String where) {
        int value=GL11.glGetError();
        if(value!=0) throw new IllegalStateException(where+" GL error "+value);
    }
    public static void main(String[] args) {
        boolean created=false;int code=0;
        try {
            Display.setDisplayMode(new DisplayMode(400,240));
            Display.setTitle("RasterIX full 256 texture validation");
            Display.create(new PixelFormat().withBitsPerPixel(16).withDepthBits(16).withStencilBits(0));
            created=true;
            if(GL11.glGetInteger(GL11.GL_MAX_TEXTURE_SIZE)!=256) throw new IllegalStateException("Expected real 256 texture profile");
            error("context");
            GL11.glReadBuffer(GL11.GL_FRONT);
            error("front buffer selection");
            GL11.glViewport(0,0,400,240);
            GL11.glMatrixMode(GL11.GL_PROJECTION);GL11.glLoadIdentity();GL11.glOrtho(0,400,0,240,-1,1);
            GL11.glMatrixMode(GL11.GL_MODELVIEW);GL11.glLoadIdentity();
            GL11.glDisable(GL11.GL_BLEND);GL11.glDisable(GL11.GL_ALPHA_TEST);
            GL11.glDisable(GL11.GL_DEPTH_TEST);GL11.glDisable(GL11.GL_LIGHTING);
            GL11.glDisable(GL11.GL_FOG);GL11.glDisable(GL11.GL_CULL_FACE);
            GL11.glEnable(GL11.GL_TEXTURE_2D);GL11.glColor4f(1,1,1,1);
            int name=GL11.glGenTextures();GL11.glBindTexture(GL11.GL_TEXTURE_2D,name);
            GL11.glTexParameteri(GL11.GL_TEXTURE_2D,GL11.GL_TEXTURE_MIN_FILTER,GL11.GL_NEAREST);
            GL11.glTexParameteri(GL11.GL_TEXTURE_2D,GL11.GL_TEXTURE_MAG_FILTER,GL11.GL_NEAREST);
            GL11.glTexEnvi(GL11.GL_TEXTURE_ENV,GL11.GL_TEXTURE_ENV_MODE,GL11.GL_REPLACE);
            ByteBuffer source=pattern(0);
            GL11.glPixelStorei(GL11.GL_UNPACK_ALIGNMENT,1);
            GL11.glTexImage2D(GL11.GL_TEXTURE_2D,0,GL11.GL_RGB,256,256,0,GL11.GL_RGB,GL11.GL_UNSIGNED_BYTE,source);
            error("full 256 upload");
            byte[] all=new byte[256*256*3];int bad=0;
            for(int epoch=0;epoch<3;epoch++) {
             if(epoch==1) {
                GL11.glTexSubImage2D(GL11.GL_TEXTURE_2D,0,0,0,256,256,GL11.GL_RGB,GL11.GL_UNSIGNED_BYTE,pattern(1));
                error("full texture re-encoding, preserving every address bit across both images");
             }
             if(epoch==2) {
                ByteBuffer patch=BufferUtils.createByteBuffer(16*16*3);
                for(int i=0;i<256;i++) patch.put((byte)0).put((byte)252).put((byte)0);
                patch.flip();
                GL11.glTexSubImage2D(GL11.GL_TEXTURE_2D,0,120,120,16,16,GL11.GL_RGB,GL11.GL_UNSIGNED_BYTE,patch);
                error("dynamic subimage crossing 128 boundary");
             }
             for(int part=0;part<2;part++) {
                GL11.glClearColor(0,0,0,1);GL11.glClear(GL11.GL_COLOR_BUFFER_BIT);
                float t0=part*.5f,t1=t0+.5f;
                GL11.glBegin(GL11.GL_QUADS);
                GL11.glTexCoord2f(0,t0);GL11.glVertex2f(0,0);
                GL11.glTexCoord2f(1,t0);GL11.glVertex2f(256,0);
                GL11.glTexCoord2f(1,t1);GL11.glVertex2f(256,128);
                GL11.glTexCoord2f(0,t1);GL11.glVertex2f(0,128);GL11.glEnd();
                Display.swapBuffers();error("swap before front-buffer readback");
                ByteBuffer read=BufferUtils.createByteBuffer(256*128*4);
                GL11.glReadPixels(0,0,256,128,GL11.GL_RGBA,GL11.GL_UNSIGNED_BYTE,read);
                error("render/readback strip "+part);
                for(int y=0;y<128;y++) for(int x=0;x<256;x++) {
                    int at=(y*256+x)*4,r=read.get(at)&255,g=read.get(at+1)&255,b=read.get(at+2)&255;
                    int index=(part*128+y)*256+x;
                    int fullY=part*128+y;
                    int expected=(epoch==2&&x>=120&&x<136&&fullY>=120&&fullY<136)?0x07e0:texel(index,epoch);
                    int observed=((r>>3)<<11)|((g>>2)<<5)|(b>>3);
                    // Existing framebuffer has 5 bits per color; mask only green's extra transport bit.
                    if((observed&0xffdf)!=(expected&0xffdf)) {
                        if(bad<8) System.out.println("JAVA256_PIXEL_MISMATCH "+index+" epoch="+epoch+" got="+observed+" expected="+expected);
                        bad++;
                    }
                    int output=((255-(part*128+y))*256+x)*3;
                    all[output]=(byte)r;all[output+1]=(byte)g;all[output+2]=(byte)b;
                }
            }
             String image=epoch==0?args[0]+".initial.ppm":epoch==1?args[0]+".rotated.ppm":args[0];
             try(FileOutputStream f=new FileOutputStream(image)) {
                f.write("P6\n256 256\n255\n".getBytes("US-ASCII"));f.write(all);
             }
            }
            GL11.glDeleteTextures(name);
            System.out.println("JAVA256_TEXTURE_CHECK pixels=196608 mismatches="+bad+" mask=0xffdf encodings=identity16,rotl1_16 dynamic_subimage=16x16@120,120 resampled=0");
            if(bad!=0) throw new IllegalStateException("Incorrect texture sampling");
            System.out.println("JAVA256_TEXTURE_PASS");
        } catch(Throwable failure) {code=2;failure.printStackTrace();}
        finally {if(created) Display.destroy();}
        System.exit(code);
    }
}
