from datetime import datetime, timezone, timedelta
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
