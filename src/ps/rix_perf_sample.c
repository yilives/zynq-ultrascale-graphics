/* SPDX-License-Identifier: MIT
 * Read-only per-thread CPU-clock sampling. No GPU/FPGA mappings or signals.
 */
#define _GNU_SOURCE
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <time.h>
struct count { uint64_t ip,n;uint32_t tid; };
struct event { int fd;void *map;size_t bytes; };
static struct count counts[65536];
static uint64_t samples,lost,dropped,corrupt;
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static void add(uint64_t ip,uint32_t tid){
    unsigned h=(unsigned)(((ip>>2)*11400714819323198485ull)^tid)&65535;
    for(unsigned i=0;i<65536;i++,h=(h+1)&65535){
        if(!counts[h].n || (counts[h].ip==ip&&counts[h].tid==tid)){
            counts[h].ip=ip;counts[h].tid=tid;counts[h].n++;samples++;return;
        }
    }
    dropped++;
}
static void ringcopy(void *dst,const unsigned char *ring,size_t size,uint64_t pos,size_t bytes){
    size_t off=(size_t)(pos%size),first=size-off;if(first>bytes)first=bytes;
    memcpy(dst,ring+off,first);if(first<bytes)memcpy((unsigned char*)dst+first,ring,bytes-first);
}
static void drain(struct event *e){
    struct perf_event_mmap_page *p=e->map;
    uint64_t head=__atomic_load_n(&p->data_head,__ATOMIC_ACQUIRE),tail=p->data_tail;
    size_t size=p->data_size;const unsigned char *ring=(const unsigned char*)e->map+p->data_offset;
    if(!size||head-tail>size){corrupt++;__atomic_store_n(&p->data_tail,head,__ATOMIC_RELEASE);return;}
    while(tail<head){
        struct perf_event_header h;ringcopy(&h,ring,size,tail,sizeof(h));
        if(h.size<sizeof(h)||h.size>size||tail+h.size>head){corrupt++;tail=head;break;}
        if(h.type==PERF_RECORD_SAMPLE && h.size>=24 && (h.misc&PERF_RECORD_MISC_CPUMODE_MASK)==PERF_RECORD_MISC_USER){
            struct {uint64_t ip;uint32_t pid,tid;} sample;
            ringcopy(&sample,ring,size,tail+sizeof(h),sizeof(sample));add(sample.ip,sample.tid);
        }else if(h.type==PERF_RECORD_LOST && h.size>=24){
            uint64_t payload[2];ringcopy(payload,ring,size,tail+sizeof(h),sizeof(payload));lost+=payload[1];
        }
        tail+=h.size;
    }
    __atomic_store_n(&p->data_tail,tail,__ATOMIC_RELEASE);
}
int main(int argc,char **argv){
    if(argc<4||argc>11)return 2;
    double seconds=strtod(argv[1],NULL);if(seconds<1||seconds>180)return 2;
    struct event events[8];memset(events,0,sizeof(events));
    int n=0,error=0;const char *stage="open";
    double start=now();
    for(int i=3;i<argc;i++){
        long tid=strtol(argv[i],NULL,10);if(tid<=0){error=EINVAL;goto done;}
        struct perf_event_attr a;memset(&a,0,sizeof(a));a.size=sizeof(a);
        a.type=PERF_TYPE_SOFTWARE;a.config=PERF_COUNT_SW_CPU_CLOCK;
        a.sample_period=10000000;a.sample_type=PERF_SAMPLE_IP|PERF_SAMPLE_TID;
        a.disabled=1;a.exclude_kernel=1;a.exclude_hv=1;a.wakeup_events=1;
        int fd=(int)syscall(__NR_perf_event_open,&a,(pid_t)tid,-1,-1,PERF_FLAG_FD_CLOEXEC);
        if(fd<0){error=errno;goto done;}
        size_t bytes=(size_t)sysconf(_SC_PAGESIZE)*17;
        void *map=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
        if(map==MAP_FAILED){error=errno;close(fd);stage="mmap";goto done;}
        events[n++]=(struct event){fd,map,bytes};
    }
    for(int i=0;i<n;i++)if(ioctl(events[i].fd,PERF_EVENT_IOC_ENABLE,0)){error=errno;stage="enable";goto done;}
    start=now();
    while(now()-start<seconds){for(int i=0;i<n;i++)drain(&events[i]);usleep(5000);}
done:
    for(int i=0;i<n;i++){ioctl(events[i].fd,PERF_EVENT_IOC_DISABLE,0);drain(&events[i]);munmap(events[i].map,events[i].bytes);close(events[i].fd);}
    FILE *out=fopen(argv[2],"wx");if(!out){perror("profile output");return 2;}
    int passed=!error&&samples&&!lost&&!dropped&&!corrupt;
    fprintf(out,"{\"passed\":%s,\"errno\":%d,\"stage\":\"%s\",\"seconds\":%.9f,\"period_ns\":10000000,\"events\":%d,\"samples\":%llu,\"lost\":%llu,\"dropped\":%llu,\"corrupt\":%llu,\"counts\":[",
        passed?"true":"false",error,stage,now()-start,n,(unsigned long long)samples,(unsigned long long)lost,(unsigned long long)dropped,(unsigned long long)corrupt);
    int first=1;for(unsigned i=0;i<65536;i++)if(counts[i].n){
        fprintf(out,"%s{\"tid\":%u,\"ip\":\"0x%llx\",\"samples\":%llu}",first?"":",",counts[i].tid,(unsigned long long)counts[i].ip,(unsigned long long)counts[i].n);first=0;
    }
    fputs("]}\n",out);fclose(out);
    printf("CPU_SAMPLE_RESULT passed=%d errno=%d samples=%llu lost=%llu\n",passed,error,(unsigned long long)samples,(unsigned long long)lost);
    return passed?0:1;
}
