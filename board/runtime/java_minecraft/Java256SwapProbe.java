import java.nio.ByteBuffer;
import org.lwjgl.BufferUtils;
import org.lwjgl.opengl.*;

/** Fast full-frame GPU clears and swaps; hardware frame accounting is external. */
public final class Java256SwapProbe {
    public static final int FRAMES=121;
    public static void main(String[] args){boolean created=false;int code=0;
        try {
            Display.setDisplayMode(new DisplayMode(400,240));Display.setTitle("RasterIX swap fence stress");
            Display.create(new PixelFormat().withBitsPerPixel(16).withDepthBits(16).withStencilBits(0));created=true;
            GL11.glViewport(0,0,400,240);GL11.glReadBuffer(GL11.GL_FRONT);
            for(int n=0;n<FRAMES;n++){
                GL11.glClearColor(n%3==0?1:0,n%3==1?1:0,n%3==2?1:0,1);
                GL11.glClear(GL11.GL_COLOR_BUFFER_BIT);Display.update();
            }
            ByteBuffer pixel=BufferUtils.createByteBuffer(4);
            GL11.glReadPixels(200,120,1,1,GL11.GL_RGBA,GL11.GL_UNSIGNED_BYTE,pixel);
            int r=pixel.get(0)&0xf8,g=pixel.get(1)&0xf8,b=pixel.get(2)&0xf8;
            if(r!=0xf8||g!=0||b!=0||GL11.glGetError()!=0)throw new IllegalStateException("Final red GPU frame mismatch "+r+","+g+","+b);
            System.out.println("JAVA256_SWAP_PASS frames="+FRAMES+" final_color=red framebuffer=400x240");
        }catch(Throwable failure){failure.printStackTrace();code=1;}
        finally{if(created)try{Display.destroy();}catch(Throwable failure){failure.printStackTrace();code=1;}}
        System.exit(code);
    }
}
