/* Diagnostic-only JNI error attribution. Pending GL errors are returned to the
 * original Java glGetError caller. Never use this build for FPS acceptance. */
#include <dlfcn.h>
#include <stdio.h>
static __thread unsigned int pending;
static __thread int primitive;
static unsigned int reports;
void rix_mali_diag_post(const char *name,int mode) {
    if(mode==1){primitive=1;return;}
    if(mode==2)primitive=0;
    if(primitive)return;
    unsigned int (*get)(void)=dlsym(RTLD_DEFAULT,"glGetError");
    if(!get)return;
    unsigned int error=get();
    if(error) {
        if(!pending)pending=error;
        if(__atomic_fetch_add(&reports,1,__ATOMIC_RELAXED)<64) {
            fprintf(stdout,"MALI_DIAGNOSTIC_ERROR after=%s error=%u\n",name,error);fflush(stdout);
        }
    }
}
unsigned int rix_mali_diag_get_error(unsigned int (*get)(void)) {
    if(pending){unsigned int result=pending;pending=0;return result;}
    return get();
}
