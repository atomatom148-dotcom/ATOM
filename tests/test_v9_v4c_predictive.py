from datetime import datetime, timezone, timedelta
from dataclasses import replace
import math
import random
import time

import pytest

from quant.v9_v4c_predictive import *

NOW=datetime(2026,1,1,tzinfo=timezone.utc)

def test_method_identities_and_nearest_rank():
    assert nearest_rank([1,2,3,4],.75)==3
    assert nearest_rank([1,2,3,4],.9)==4
    assert nearest_rank([1,1,9,9],.75)==9
    assert {THRESHOLD_METHOD,HAC_METHOD,HAC_LAG_METHOD,NORMAL_CDF_METHOD,NORMAL_PPF_METHOD,
            HOLM_METHOD,RELIABILITY_METHOD,GAMMA_METHOD,Q3_PARTITION_METHOD,Q3_HOLM_METHOD}

def test_scale_and_threshold_evidence_gates():
    rng=random.Random(31)
    rows=[CalibrationObservation(NOW+timedelta(minutes=i),str(i),rng.random()*20,0,4,str(i%20)) for i in range(500)]
    scale=calibrate_scale(rows[:250])
    expected=sum(x.actual_bps**2/4 for x in rows[:250])/250
    assert scale.kappa_squared==pytest.approx(expected) and scale.kappa==pytest.approx(math.sqrt(expected))
    assert calibrate_scale([CalibrationObservation(NOW,"x",1,0,0,"s")]).kappa is None
    thresholds=build_thresholds(rows)
    assert thresholds.status=="MATURE"
    assert thresholds.medium_bps==nearest_rank([abs(x.actual_bps) for x in rows],.75)
    assert build_thresholds(rows[:499]).status=="UNAVAILABLE"

def test_empirical_cdf_ties_and_probabilities():
    z=(-1.,0.,0.,2.)
    assert empirical_cdfs(z,0)==(3.5/5,1.5/5)
    assert 0 < empirical_cdfs(z,-100)[0] < 1
    assert 0 < empirical_cdfs(z,100)[0] < 1

def test_normal_and_hac_fixtures():
    assert normal_cdf(0)==.5
    assert normal_cdf(math.inf)==1 and normal_cdf(-math.inf)==0
    for p in (.001,.025,.5,.975,.999):
        assert normal_cdf(normal_ppf(p))==pytest.approx(p,abs=1e-12)
        assert normal_ppf(p)==pytest.approx(-normal_ppf(1-p),abs=2e-9)
    assert hac([1]*20).reason_codes==("HAC_VARIANCE_ZERO",)
    result=hac([(-1)**i*i/100 for i in range(100)])
    assert result.lag==math.floor(4*(100/100)**(2/9)) and result.omega>0

def test_holm_order_ties_and_stepdown():
    got=holm([.001,.001,.02,.9,1,1])
    assert [x.rank for x in got[:2]]==[1,2]
    assert got[0].threshold==pytest.approx(.05/6)
    assert not got[2].passed and not got[3].passed

@pytest.mark.parametrize("n,sizes",[(10,(2,2,2,2,2)),(11,(3,2,2,2,2)),
    (12,(3,3,2,2,2)),(13,(3,3,3,2,2)),(14,(3,3,3,3,2)),(15,(3,3,3,3,3))])
def test_reliability_initial_sizes(n,sizes):
    rows=[ReliabilityObservation(i/n,i%2,NOW+timedelta(minutes=i),str(i)) for i in range(n)]
    assert reliability(rows).initial_sizes==sizes

def test_reliability_ties_and_permutation_invariance():
    rows=[ReliabilityObservation(0.5,i%2,NOW+timedelta(minutes=i),f"{i:03}") for i in range(150)]
    a=reliability(rows); random.Random(7).shuffle(rows); b=reliability(rows)
    assert len(a.bins)==1 and a==b and a.removed_boundaries==(1,2,3,4)
    assert reliability(rows[:4]).reason_codes==("RELIABILITY_BIN_COUNT_INSUFFICIENT",)

def test_gamma_optimizer_baseline_and_interior_and_failure():
    baseline=optimize_gamma([GammaInput(1,1,1),GammaInput(2,1,1)])
    assert baseline.eta==0 and baseline.gamma==0 and baseline.status=="INACTIVE"
    data=[GammaInput(.2,1,.1),GammaInput(3,1,3)]*30
    result=optimize_gamma(data)
    assert result.status=="INACTIVE" and 0<=result.eta<1 and result.gamma>=0
    assert 0.0 in dict(result.evaluations)
    failed=optimize_gamma(data,maximum_iterations=1)
    assert failed.reason_codes==("GAMMA_OPTIMIZER_DID_NOT_CONVERGE",)

def test_range_order_statistic_and_provisional_not_published():
    scores=[float(i) for i in range(250)]
    validation=[(0.,-1.,1.,str(i%20)) for i in range(250)]
    state=calibrate_range(scores,validation,[str(i) for i in range(20)])
    assert state.quantile==sorted(scores)[math.ceil(251*.9)-1]
    assert state.status!="MATURE"

def test_live_final_mean_immutable_and_unavailable_components_null():
    from quant.v9_v3_synthesis import V3HorizonResult
    v3=V3HorizonResult("30S",30,10.,4.,"AVAILABLE",(),(),0,None)
    compact=CompactHorizonState("30S","UNAVAILABLE",None,None,"UNAVAILABLE",None,None,
        "PROVISIONAL",2.,(),("UNAVAILABLE",)*6)
    final=final_numbers(v3,compact)
    assert final.final_bps==10 and final.move_percent==100*math.expm1(.001)
    assert final.predictive_scale_bps is None and final.range_lower_bps is None
    assert final.probability_positive is None and (final.gamma,final.phi,final.gamma_status)==(0,1,"INACTIVE")

def test_offline_blocks_enforce_proof_timing_cohort_conflicts_and_overlap():
    rows=[]
    for i in range(9):
        rows.append(CalibrationObservation(NOW+timedelta(seconds=10*i),str(i),1,0,1,"s",
            i!=8,"VERIFIED","c","h",NOW+timedelta(seconds=10*i),20))
    # Duplicate identical records are canonical; an incompatible duplicate contaminates its key.
    rows.extend((rows[1],replace(rows[2],actual_bps=2)))
    blocks=construct_evidence_blocks(rows,cohort_id="c",cohort_hash="h",
        threshold_end=NOW+timedelta(seconds=30),calibration_end=NOW+timedelta(seconds=60),
        validation_end=NOW+timedelta(seconds=90))
    assert [x.forecast_record_id for x in blocks.threshold]==["0"]
    assert all(a.cutoff+timedelta(seconds=a.horizon_seconds)<=b.cutoff
               for group in (blocks.threshold,blocks.calibration,blocks.validation)
               for a,b in zip(group,group[1:]))
    assert "8" not in [x.forecast_record_id for x in blocks.validation]

def test_probability_calibration_is_six_separate_events_and_preserves_zero_mass():
    cal=[ProbabilityHoldoutObservation(NOW+timedelta(minutes=i),str(i),float((i%11)-5),0,2) for i in range(500)]
    hold=[ProbabilityHoldoutObservation(NOW+timedelta(days=1,minutes=i),f"h{i}",float((i%13)-6),0,2) for i in range(500)]
    residuals,events=calibrate_probability_events(cal,hold,medium_bps=3,large_bps=5)
    assert len(residuals)==500 and tuple(x.event for x in events)==EVENTS
    assert all(x.calibration_n==500 and x.holm_rank in range(1,7) for x in events)
    probabilities=event_probabilities(residuals,0,2,3,5)
    assert len(probabilities)==6 and all(0<p<1 for p in probabilities)

def test_q3_partition_ties_and_degradation_orientation():
    tied=[GammaInput(i+1,1,1,NOW+timedelta(minutes=i),str(i)) for i in range(8)]
    assert q3_quartile_diagnostics(tied,.2,1).reason_codes==("Q3_QUARTILE_TIE_COLLAPSE",)
    rows=[GammaInput((i%5)+1,2,float(i+1),NOW+timedelta(minutes=i),str(i)) for i in range(240)]
    result=q3_quartile_diagnostics(rows,.2,sum(x.magnitude**2 for x in rows)/len(rows))
    assert result.initial_sizes==(60,60,60,60) and len(result.quartiles)==4
    assert all(x.minimum_magnitude<=x.maximum_magnitude for x in result.quartiles)

def test_state_hash_includes_diagnostics_and_rejects_active_gamma():
    horizons=tuple(CompactHorizonState(h,"UNAVAILABLE",None,None,"UNAVAILABLE",None,None,
        "UNAVAILABLE",None,(),("UNAVAILABLE",)*6) for h in HORIZONS)
    state=build_v4c_state(symbol="COIN",cohort_id="c",state_as_of=NOW,horizons=horizons)
    assert state.state_id=="v9v4state:"+state.state_hash and len(state.state_hash)==64
    with pytest.raises(ValueError,match="production gamma"):
        replace(state,gamma=1)

def test_live_100000_six_horizon_p99_benchmark():
    from quant.v9_v3_synthesis import V3HorizonResult
    compact=CompactHorizonState("30S","MATURE",3,5,"MATURE",1,1,"MATURE",2,
        (-2.,-1.,0.,1.,2.),("MATURE",)*6)
    result=V3HorizonResult("30S",30,1.,1.,"AVAILABLE",(),(),0,None)
    durations=[]
    for _ in range(100_000):
        start=time.perf_counter()
        for __ in range(6): final_numbers(result,compact)
        durations.append(time.perf_counter()-start)
    assert sorted(durations)[98_999] <= .010
