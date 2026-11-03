import java.nio.FloatBuffer;
import org.lwjgl.BufferUtils;
import org.lwjgl.opengl.*;

/** Invalid unit calls must report errors without changing valid unit state. */
public final class Java256TmuProbe {
    static void check(boolean condition,String message){if(!condition)throw new IllegalStateException(message);}
    static void error(int expected,String where){int actual=GL11.glGetError();check(actual==expected,where+" expected="+expected+" actual="+actual);}
    static float[] coordinates(){FloatBuffer b=BufferUtils.createFloatBuffer(4);GL11.glGetFloat(GL11.GL_CURRENT_TEXTURE_COORDS,b);return new float[]{b.get(0),b.get(1),b.get(2),b.get(3)};}
    public static void main(String[] args){boolean created=false;int code=0;
        try {
            Display.setDisplayMode(new DisplayMode(400,240));
            Display.setTitle("RasterIX checked texture units");Display.create(new PixelFormat().withBitsPerPixel(16).withDepthBits(16).withStencilBits(0));created=true;
            check(GL11.glGetInteger(GL13.GL_MAX_TEXTURE_UNITS)==1,"One real hardware TMU required");error(0,"context");
            GL13.glActiveTexture(GL13.GL_TEXTURE0);GL13.glClientActiveTexture(GL13.GL_TEXTURE0);
            int texture=GL11.glGenTextures();GL11.glBindTexture(GL11.GL_TEXTURE_2D,texture);
            GL13.glMultiTexCoord4f(GL13.GL_TEXTURE0,.125f,.25f,.5f,1f);error(0,"valid unit0");
            float[] before=coordinates();error(0,"coordinate query");
            float[] expected={.125f,.25f,.5f,1f};for(int i=0;i<4;i++)check(before[i]==expected[i],"valid unit coordinates not stored");
            int cases=0;
            for(int invalid:new int[]{GL13.GL_TEXTURE0-1,GL13.GL_TEXTURE1,-1}) {
                GL13.glActiveTexture(invalid);error(GL11.GL_INVALID_ENUM,"active invalid");
                check(GL11.glGetInteger(GL13.GL_ACTIVE_TEXTURE)==GL13.GL_TEXTURE0,"active unit mutated");
                check(GL11.glGetInteger(GL11.GL_TEXTURE_BINDING_2D)==texture,"binding mutated");error(0,"active state");cases++;
                GL13.glClientActiveTexture(invalid);error(GL11.GL_INVALID_ENUM,"client invalid");
                check(GL11.glGetInteger(GL13.GL_CLIENT_ACTIVE_TEXTURE)==GL13.GL_TEXTURE0,"client unit mutated");error(0,"client state");cases++;
                GL13.glMultiTexCoord4f(invalid,.9f,.8f,.7f,.6f);error(GL11.GL_INVALID_ENUM,"coordinate invalid");
                float[] after=coordinates();for(int i=0;i<4;i++)check(before[i]==after[i],"coordinates mutated");error(0,"coordinate state");cases++;
                GL13.glMultiTexCoord2f(invalid,.7f,.6f);error(GL11.GL_INVALID_ENUM,"world lightmap API invalid");
                after=coordinates();for(int i=0;i<4;i++)check(before[i]==after[i],"lightmap coordinates mutated");error(0,"lightmap state");cases++;
            }
            System.out.println("JAVA256_TMU_PASS cases="+cases+" state_preserved=1 real_tmu_count=1");
        }catch(Throwable failure){failure.printStackTrace();code=1;}
        finally{if(created)try{Display.destroy();}catch(Throwable failure){failure.printStackTrace();code=1;}}
        System.exit(code);
    }
}
