from datetime import datetime, timezone, timedelta
from dataclasses import replace
import math
import random

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
    rows=[CalibrationObservation(NOW+timedelta(minutes=i),str(i),rng.random()*20,0,4,str(i%20),
                                 NOW+timedelta(minutes=i,seconds=1)) for i in range(500)]
    boundary=NOW+timedelta(minutes=500)
    scale=calibrate_scale(rows[:250],calibration_end=boundary)
    expected=sum(x.actual_bps**2/4 for x in rows[:250])/250
    assert scale.kappa_squared==pytest.approx(expected) and scale.kappa==pytest.approx(math.sqrt(expected))
    assert calibrate_scale([CalibrationObservation(NOW,"x",1,0,0,"s",NOW)],calibration_end=boundary).kappa is None
    thresholds=build_thresholds(rows,reference_end=boundary)
    assert thresholds.status=="MATURE"
    assert thresholds.medium_bps==nearest_rank([abs(x.actual_bps) for x in rows],.75)
    assert build_thresholds(rows[:499],reference_end=boundary).status=="UNAVAILABLE"

def test_block_boundary_excludes_late_resolutions():
    rows=[CalibrationObservation(NOW,str(i),float(i+1),0,1,str(i%20),NOW+timedelta(days=2))
          for i in range(500)]
    boundary=NOW+timedelta(days=1)
    assert calibrate_scale(rows,calibration_end=boundary).raw_n==0
    assert build_thresholds(rows,reference_end=boundary).raw_n==0

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
    invalid=optimize_gamma([GammaInput(1e308,1,1)])
    assert invalid.reason_codes==("GAMMA_OBJECTIVE_UNAVAILABLE",)

def test_gamma_final_candidate_tolerance_tie_selects_smallest(monkeypatch):
    import quant.v9_v4c_predictive as module
    monkeypatch.setattr(module,"gamma_objective",lambda inputs,eta,m2: 1.0+eta*EPSILON)
    result=module.optimize_gamma([GammaInput(1,1,1)])
    assert result.eta==0 and result.gamma==0

def test_range_order_statistic_and_provisional_not_published():
    scores=[float(i) for i in range(250)]
    validation=[RangeValidationObservation(0.,-1.,1.,str(i%20),NOW,NOW) for i in range(250)]
    state=calibrate_range(scores,validation,[str(i) for i in range(20)],validation_end=NOW)
    assert state.quantile==sorted(scores)[math.ceil(251*.9)-1]
    assert state.status!="MATURE"

def test_live_final_mean_immutable_and_unavailable_components_null():
    from quant.v9_v3_synthesis import V3HorizonResult
    v3=V3HorizonResult("30S",30,10.,4.,"AVAILABLE",(),(),0,None)
    compact=CompactHorizonState("30S","UNAVAILABLE",None,None,"UNAVAILABLE",None,None,
        "PROVISIONAL",2.,(),("UNAVAILABLE",)*6)
    final=final_numbers(v3,compact)
    assert final.final_bps==10 and final.move_percent==100*math.expm1(.001)
    assert final.direction=="EXPECTED_UP"
    assert final.predictive_scale_bps is None and final.range_lower_bps is None
    assert final.probability_positive is None and (final.gamma,final.phi,final.gamma_status)==(0,1,"INACTIVE")

def _six_states(**changes):
    return tuple(CompactHorizonState(h,"UNAVAILABLE",None,None,"UNAVAILABLE",None,None,
        "UNAVAILABLE",None,(),("UNAVAILABLE",)*6,**changes) for h in HORIZONS)

def test_state_time_and_hash_fail_closed_on_insert_and_select():
    with pytest.raises(ValueError,match="ordered"):
        build_v4c_state(symbol="X",cohort_id="c",state_as_of=NOW,
                        evidence_first_cutoff=NOW,evidence_last_cutoff=NOW+timedelta(seconds=1),horizons=_six_states())
    state=build_v4c_state(symbol="X",cohort_id="c",state_as_of=NOW,
        evidence_first_cutoff=NOW,evidence_last_cutoff=NOW,horizons=_six_states())
    class Cursor:
        def __init__(self):self.results=[];self.inserted=None
        def execute(self,sql,args):
            if sql.startswith("SELECT state_hash FROM"):self.results=[]
            elif sql.startswith("INSERT INTO"):self.inserted=args
        def fetchall(self):return self.results
    class Connection:
        def __init__(self):self.value=Cursor()
        def cursor(self):return self.value
    connection=Connection(); store=V4CStateStore(connection)
    assert store.insert(replace(state,state_hash="0"*64),NOW)=="STATE_HASH_MISMATCH"
    assert store.insert(state,NOW)=="INSERT"
    canonical=connection.value.inserted[9]
    connection.value.execute=lambda sql,args:setattr(connection.value,"results",[(state.state_hash,canonical,NOW,NOW,NOW)])
    assert store.latest_json(symbol="X",cohort_id="c",requested_cutoff=NOW)[1]=="AVAILABLE"
    tampered=canonical.replace('"symbol": "X"','"symbol": "Y"')
    connection.value.execute=lambda sql,args:setattr(connection.value,"results",[(state.state_hash,tampered,NOW,NOW,NOW)])
    assert store.latest_json(symbol="X",cohort_id="c",requested_cutoff=NOW)[1]=="STATE_HASH_MISMATCH"

def test_mature_statuses_fail_closed_when_live_numerics_missing():
    from quant.v9_v3_synthesis import V3HorizonResult
    v3=V3HorizonResult("30S",30,1.,0.,"AVAILABLE",(),(),0,None)
    state=CompactHorizonState("30S","MATURE",1.,2.,"MATURE",1.,1.,"MATURE",1.,
                              (-1.,0.,1.),("MATURE",)*6)
    result=final_numbers(v3,state)
    assert result.range_status=="UNAVAILABLE"
    assert result.probability_status==("UNAVAILABLE",)*6

def test_state_version_first_boundary_and_paired_boundaries_are_hashed():
    with pytest.raises(ValueError,match="both"):
        build_v4c_state(symbol="X",cohort_id="c",state_as_of=NOW,
            evidence_first_cutoff=NOW,evidence_last_cutoff=None,horizons=_six_states())
    state=build_v4c_state(symbol="X",cohort_id="c",state_as_of=NOW,
        evidence_first_cutoff=NOW,evidence_last_cutoff=NOW,horizons=_six_states())
    assert state.state_version==PROBABILITY_STATE_VERSION and state.evidence_first_cutoff==NOW

def test_range_validation_rejects_late_resolution():
    row=RangeValidationObservation(0.,-1.,1.,"s",NOW,NOW+timedelta(seconds=1))
    result=calibrate_range([1.]*250,[row],["s"],validation_end=NOW)
    assert result.validation_n==0

def test_probability_six_event_builder_and_independent_statuses():
    calibration={event:tuple(i%2 for i in range(500)) for event in EVENTS}
    holdout=[]
    for event in EVENTS:
        holdout.extend(ProbabilityObservation(event,.5,i%2,NOW+timedelta(days=1,seconds=i),
            f"{event}-{i}",NOW+timedelta(days=1,seconds=i)) for i in range(500))
    result=calibrate_probabilities(calibration_outcomes=calibration,holdout=holdout,
        calibration_end=NOW,holdout_end=NOW+timedelta(days=2))
    assert tuple(x.event for x in result)==EVENTS and len(result)==6
    assert all(x.status in ("PROVISIONAL","MATURE") for x in result)

def test_q3_four_way_partition_ties_holm_and_chronology():
    rng=random.Random(81)
    rows=[Q3Observation(float(i),rng.uniform(-1,1),NOW+timedelta(seconds=i),str(i))
          for i in range(400)]
    result=q3_quartile_degradation(rows)
    assert result.initial_sizes==(100,100,100,100) and len(result.quartiles)==4
    assert result.status in ("PASS","FAIL")
    collapsed=q3_quartile_degradation([replace(x,magnitude=1.) for x in rows])
    assert collapsed.reason_codes==("Q3_QUARTILE_TIE_COLLAPSE",)

@pytest.mark.parametrize("field",("expected_return_bps","predictive_variance_bps2"))
def test_live_never_publishes_nonfinite_values(field):
    from quant.v9_v3_synthesis import V3HorizonResult
    values=dict(horizon="30S",horizon_seconds=30,expected_return_bps=1.,predictive_variance_bps2=1.,
        status="AVAILABLE",used_quant_ids=(),weights=(),directional_input_count=0,covariance_mode=None)
    values[field]=math.inf
    state=CompactHorizonState("30S","MATURE",1.,2.,"MATURE",1.,1.,"MATURE",1.,
                              (-1.,0.,1.),("MATURE",)*6)
    output=final_numbers(V3HorizonResult(**values),state)
    published=(output.final_bps,output.move_percent,output.predictive_scale_bps,
               output.range_lower_bps,output.range_upper_bps,
               output.probability_positive,output.probability_negative)
    assert all(value is None or math.isfinite(value) for value in published)

def test_nonfinite_quantile_and_thresholds_fail_closed():
    from quant.v9_v3_synthesis import V3HorizonResult
    state=CompactHorizonState("30S","MATURE",math.inf,math.nan,"MATURE",1.,1.,"MATURE",math.inf,
                              (-1.,0.,1.),("MATURE",)*6)
    output=final_numbers(V3HorizonResult("30S",30,1.,1.,"AVAILABLE",(),(),0,None),state)
    assert output.medium_threshold_bps is None and output.large_threshold_bps is None
    assert output.range_status=="UNAVAILABLE" and output.probability_status[2:]==("UNAVAILABLE",)*4

def test_gamma_result_stores_objectives_and_convergence():
    result=optimize_gamma([GammaInput(.2,1,.1),GammaInput(3,1,3)]*30)
    assert all(math.isfinite(x) for x in (result.baseline_objective,result.challenger_objective,result.objective_improvement))
    assert result.objective_improvement==pytest.approx(result.baseline_objective-result.challenger_objective)
    assert result.convergence_status=="CONVERGED"
