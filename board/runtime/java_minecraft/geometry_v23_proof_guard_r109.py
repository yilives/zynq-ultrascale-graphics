"""Validate the actual v23 report without rewriting atomic-v4 evidence."""
def verify_current_v23_proof(proof, before, receipt):
    bit='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
    cnn=dict(magic=0x4e4e5332,shape=(96<<16)|160,capabilities=7,adapter_abi=0x00020001)
    assert proof['passed'] is True and proof['outcome']=='new-loaded-and-verified'
    assert len(receipt)==4 and receipt[:3]==['RIX_FSR_PL_ACTIVE_V1',before['boot_id'],bit]
    assert proof['after']['boot_id']==before['boot_id']
    assert proof['manifest']['images']['new']['sha256']==bit
    assert proof['manifest']['source_sha256']==receipt[3]
    assert proof['after']['cnn']==before['cnn']==cnn
    assert proof['after']['bindings']==before['bindings']
    assert proof['after']['modules']==before['modules']
    assert proof['after']['fsr']['passed'] is True
    assert before['manager_name']=='Xilinx ZynqMP FPGA Manager' and before['manager_state']=='operating'
    return True
