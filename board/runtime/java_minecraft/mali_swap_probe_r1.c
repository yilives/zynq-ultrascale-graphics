/* Private LWJGL integration probe; GL4ES and Minecraft remain unmodified.
 * One render-thread writer. Slots 0..7 are seqlocked; slot 8 is a capture
 * request written by the observer only after the measured interval.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <time.h>
#include <dlfcn.h>
#include <string.h>

static uint64_t *rix_mali_stats;
static uint64_t rix_mali_swap_start;
static int rix_mali_init_attempted;
static uint64_t rix_mali_now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}
static void rix_mali_probe_before(void) {
    if (!rix_mali_init_attempted) {
        rix_mali_init_attempted=1;
        const char *path=getenv("RIX_MALI_SWAP_STATS");
        if (path) {
            int fd=open(path,O_RDWR|O_CREAT|O_EXCL,0600);
            if (fd>=0 && ftruncate(fd,128)==0) {
                void *mem=mmap(NULL,128,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
                if (mem!=MAP_FAILED) {
                    rix_mali_stats=mem;
                    __atomic_store_n(rix_mali_stats,0x5249584d414c4931ULL,__ATOMIC_RELEASE);
                }
            }
            if (fd>=0)close(fd);
        }
        const unsigned char *(*get_string)(unsigned int)=dlsym(RTLD_DEFAULT,"glGetString");
        if (get_string) {
            fprintf(stdout,"MALI_RENDER_THREAD renderer=%s version=%s\n",get_string(0x1f01),get_string(0x1f02));
            fflush(stdout);
        }
    }
    if (rix_mali_stats && __atomic_load_n(rix_mali_stats+8,__ATOMIC_ACQUIRE)==1) {
        const char *capture=getenv("RIX_MALI_CAPTURE");
        void (*finish)(void)=dlsym(RTLD_DEFAULT,"glFinish");
        void (*integer)(unsigned int,int *)=dlsym(RTLD_DEFAULT,"glGetIntegerv");
        void (*read_pixels)(int,int,int,int,unsigned int,unsigned int,void *)=dlsym(RTLD_DEFAULT,"glReadPixels");
        unsigned int (*get_error)(void)=dlsym(RTLD_DEFAULT,"glGetError");
        int vp[4]={0};unsigned int err=0xffffffffU;
        if(capture && finish && integer && read_pixels && get_error) {
            finish();integer(0xba2,vp);
            if(vp[0]==0 && vp[1]==0 && vp[2]==400 && vp[3]==240) {
                unsigned char *raw=malloc(384000);
                if(raw) {
                    memset(raw,0,384000);
                    read_pixels(0,0,400,240,0x1908,0x1401,raw);err=get_error();
                    int fd=open(capture,O_WRONLY|O_CREAT|O_EXCL,0600);
                    if(fd>=0) {
                        size_t at=0;
                        while(at<384000) {ssize_t n=write(fd,raw+at,384000-at);if(n<=0)break;at+=n;}
                        close(fd);rix_mali_stats[12]=at;
                    }
                    free(raw);
                }
            }
        }
        rix_mali_stats[9]=vp[2];rix_mali_stats[10]=vp[3];rix_mali_stats[11]=err;
        rix_mali_stats[6]=rix_mali_now();rix_mali_stats[7]=rix_mali_stats[2]+1;
        __atomic_store_n(rix_mali_stats+8,2,__ATOMIC_RELEASE);
    }
    rix_mali_swap_start=rix_mali_now();
}
static void rix_mali_probe_after(void) {
    uint64_t now=rix_mali_now();
    if(rix_mali_stats) {
        __atomic_add_fetch(rix_mali_stats+1,1,__ATOMIC_ACQ_REL);
        rix_mali_stats[2]++;
        rix_mali_stats[3]=now;
        rix_mali_stats[4]+=now-rix_mali_swap_start;
        __atomic_add_fetch(rix_mali_stats+1,1,__ATOMIC_RELEASE);
    }
}
