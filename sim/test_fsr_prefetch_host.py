"""Compile only the Linux host target; exercise the actual scheduler via mock adapters."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--revision',default='r1')
revision=parser.parse_args().revision
assert revision.isascii() and revision.replace('-','').isalnum()
OUT=ROOT/'build/fsr-pl'/('runtime-prefetch-host-'+revision);OUT.mkdir(exist_ok=False)
def posix(p):
    value=p.resolve().as_posix();return '/mnt/'+value[0].lower()+value[2:]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=ROOT/'linux/postproc/rix_fsr_pl_prefetch.cpp'
before=sha(source)
test=r'''
#define RIX_FSR_PREFETCH_TEST
#include "@SOURCE@"
#include <set>
using namespace fsr_prefetch_mock;
static void check(bool ok,const char*why){if(!ok)throw std::runtime_error(why);}
static std::vector<Event> matching(Env&e,const char*kind){std::vector<Event> found;for(auto&v:e.events)if(v.kind==kind)found.push_back(v);return found;}
static void common(Env&e){
 check(!e.kernel_active&&!e.status,"kernel/snapshot did not drain");
 check(e.post==1&&e.active==1,"POST not restored");
 check(!e.load_lease_violation&&!e.cache_overlap&&!e.bank_violation,"lease/cache/bank safety violated");
 auto computes=matching(e,"COMPUTE_START");for(size_t i=1;i<computes.size();++i)check(computes[i].tag!=computes[i-1].tag,"duplicate source COMPUTE counted");
 for(auto&p:matching(e,"POST_SUBMIT"))if((p.tag&3)==2){bool done=false;for(auto&d:e.events)if(d.kind=="TAG_VALIDATED"&&d.mode==1&&d.us<=p.us)done=true;check(done,"POST before COMPUTE tag validation");}
}
static void run(const char*name,const std::function<void(Env&)>&config,double seconds,const std::function<void(Env&)>&verify={}){
 Env state;env=&state;rix_pl::stopped()=0;config(state);MockMap regs(0,0xa0010000,65536),pl(0,0xa1000000,0x1000000);Kernel kernel(0);Lease lease(regs);
 std::cout<<"CASE_BEGIN "<<name<<'\n';
 run_live_prefetch(kernel,regs,pl,lease,1,seconds,0,"");common(state);if(verify)verify(state);
 std::cout<<"PASS_CASE "<<name<<'\n';
}
int main(){try{
 run("late_prefetch_order",[](Env&){},.65,[](Env&e){
  auto starts=matching(e,"COMPUTE_START"),early=matching(e,"PREFETCH_REQUEST");check(starts.size()>=3&&!early.empty(),"not enough prefetch frames");
  for(auto&r:early){size_t i=0;while(i+1<starts.size()&&starts[i+1].us<=r.us)++i;check(i>0,"first frame prefetched without calibration");check(r.us-starts[i].us>=85000,"prefetch issued too early");check(r.us-starts[i].us<=85200,"prefetch missed calibrated lead");}
 });
 run("stop_during_compute",[](Env&e){e.stop_at=50000;},1,[](Env&e){auto stop=matching(e,"STOP");bool done=false;for(auto&d:matching(e,"K_DONE"))if(d.mode==1&&d.us>=97000)done=true;check(!stop.empty()&&done,"signal abandoned kernel");});
 run("stop_with_pending_prefetch",[](Env&e){e.stop_at=229000;},1,[](Env&e){
  auto early=matching(e,"PREFETCH_REQUEST");check(!early.empty(),"stop did not cover pending prefetch");
  for(auto&x:e.events)if(x.kind=="SNP_RELEASE"&&x.us>=e.stop_at){bool after=false;for(auto&d:e.events)if(d.kind=="K_DONE"&&d.mode==1&&d.us<=x.us&&d.us>=e.stop_at)after=true;check(after,"signal canceled SNP before draining COMPUTE");}
 });
 run("stop_during_first_snapshot",[](Env&e){e.stop_at=5000;},1,[](Env&e){check(matching(e,"LOAD_START").empty(),"LOAD issued after source wait stop");});
 run("stop_during_initial_load",[](Env&e){e.stop_at=20000;},1,[](Env&e){check(matching(e,"LOAD_START").size()==1&&matching(e,"COMPUTE_START").empty(),"stop during LOAD launched another kernel");});
 run("late_request_fallback",[](Env&e){e.compute_durations={97000,1000,97000};},.45,[](Env&e){auto s=matching(e,"COMPUTE_START");check(s.size()>=3,"late fallback stopped pipeline");for(auto&r:matching(e,"PREFETCH_REQUEST"))check(!(r.us>=s[1].us&&r.us<s[1].us+1000),"request incorrectly started before calibrated threshold");});
 run("canceled_prefetch_retry",[](Env&e){e.cancel_early_request=true;},.5,[](Env&e){check(!matching(e,"CANCEL").empty(),"cancel not exercised");});
 run("stale_prefetch_retry",[](Env&e){e.compute_durations={97000,1800000,97000};},2.25,[](Env&e){check(matching(e,"COMPUTE_START").size()>=3,"stale retry lost pipeline");});
 run("expired_prefetch_retry",[](Env&e){e.compute_durations={97000,2200000,97000};},2.65,[](Env&e){check(e.expired>0,"hardware expiry not exercised");});
 run("expiry_during_load",[](Env&e){e.inject_load_expiry=true;},.45,[](Env&e){check(!matching(e,"EXPIRE_DURING_LOAD").empty()&&!matching(e,"INVALIDATE").empty(),"expired LOAD cache not invalidated");});
 run("expiry_before_load_start",[](Env&e){e.expire_before_load_start=true;},.45,[](Env&e){check(!matching(e,"EXPIRE_BEFORE_LOAD_START").empty()&&!e.load_lease_violation,"known invalid lease issued LOAD");});
 run("duplicate_source_retry",[](Env&e){e.forced_frames={100,100,101};},.45,[](Env&e){auto loads=matching(e,"LOAD_START");check(loads.size()>1&&loads[0].tag==100&&loads[1].tag==101,"duplicate source was loaded");});
 run("source_wrap_allowed",[](Env&e){e.forced_frames={0xffffffffu,0,1};},.45,[](Env&e){auto loads=matching(e,"LOAD_START");check(loads.size()>1&&loads[1].tag==0,"valid source wrap rejected");});
 {
  Env e;env=&e;rix_pl::stopped()=0;e.cached_tag=7;Kernel kernel(0);bool caught=false;
  std::cout<<"CASE_BEGIN progress_exception_drains_kernel\n";
  try{kernel.call(1,0,0x21200000,7,7,0,[](uint64_t){throw std::runtime_error("progress failure");});}catch(const std::runtime_error&){caught=true;}
  check(caught&&!kernel.inflight&&!e.kernel_active&&e.now>=97000,"callback exception abandoned AXI master");
  check(!matching(e,"TAG_VALIDATED").empty(),"callback failure skipped final tag validation");
  std::cout<<"PASS_CASE progress_exception_drains_kernel\n";
 }
 {
  Env e;env=&e;rix_pl::stopped()=0;e.throw_after_early_request=true;MockMap regs(0,0xa0010000,65536),pl(0,0xa1000000,0x1000000);Kernel kernel(0);Lease lease(regs);bool caught=false;
  std::cout<<"CASE_BEGIN request_exception_drains_and_restores\n";
  try{run_live_prefetch(kernel,regs,pl,lease,1,.6,0,"");}catch(const std::runtime_error&){caught=true;}
  check(caught&&!kernel.inflight,"request exception escaped with active kernel");common(e);
  std::cout<<"PASS_CASE request_exception_drains_and_restores\n";
 }
 {
  Env e;env=&e;rix_pl::stopped()=0;e.cached_tag=7;e.never_complete=true;Kernel kernel(0);bool caught=false;
  std::cout<<"CASE_BEGIN kernel_timeout_quarantines\n";
  try{kernel.call(1,0,0x21200000,7,7);}catch(const FailStop&){caught=true;}
  check(caught&&kernel.inflight&&e.quarantined&&e.receipt_revoked,"timeout released ownership instead of quarantining");
  check(matching(e,"POST_SUBMIT").empty(),"timeout published incomplete frame");
  std::cout<<"PASS_CASE kernel_timeout_quarantines\n";
 }
 std::cout<<"PASS FSR_PREFETCH_HOST 16 cases\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL FSR_PREFETCH_HOST "<<e.what()<<'\n';return 1;}}
'''.replace('@SOURCE@',posix(source))
(OUT/'test.cpp').write_text(test)
record={'passed':False,'source_sha256':before,'FPGA_execution_included':False,'target_SDK_compilation_included':False}
def execute(args):
    return subprocess.run(['wsl.exe','-d','Ubuntu','--exec',*args],text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=120)
try:
    includes=['-I'+posix(ROOT/'build/fsr-pl/fixed-v8/runtime')]
    common=['g++','-std=c++17','-O2','-Wall','-Wextra','-pthread',*includes]
    result=execute([*common,posix(source),'-o',posix(OUT/'rix-fsr-pl-host')])
    (OUT/'host-build.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stderr
    result=execute([posix(OUT/'rix-fsr-pl-host'),'--help']);assert result.returncode==0,result.stderr
    result=execute([*common,'-Wno-unused-function',posix(OUT/'test.cpp'),'-o',posix(OUT/'test-prefetch')])
    (OUT/'mock-build.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stderr
    result=execute([posix(OUT/'test-prefetch')]);(OUT/'test.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    cases=[];metrics={};current=None
    for line in result.stdout.splitlines():
        if line.startswith('CASE_BEGIN '):current=line[11:]
        if line.startswith('{'):metrics[current]=json.loads(line)
        if line.startswith('PASS_CASE '):cases.append(line[10:])
    assert len(cases)==16 and len(set(cases))==16,cases
    for value in metrics.values():assert value['unique_source_frames']==value['frames'] and value['repeated_source_frames']==0
    assert metrics['late_prefetch_order']['prefetch_inputs_used']>0
    assert metrics['late_request_fallback']['prefetch_without_request']>0
    assert metrics['canceled_prefetch_retry']['prefetch_canceled_retries']>0
    assert metrics['stale_prefetch_retry']['prefetch_stale_dropped']>0
    assert metrics['expired_prefetch_retry']['prefetch_lease_expirations']>0
    assert metrics['duplicate_source_retry']['duplicate_snapshot_retries']>0
    assert sha(source)==before,'Runtime changed during host checks'
    record.update(passed=True,cases=cases,metrics=metrics,
        mock_support_sha256=sha(ROOT/'sim/fixtures/fsr_prefetch_mock.hpp'))
finally:
    (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('FSR_PREFETCH_HOST_PASS',len(record['cases']),OUT)
