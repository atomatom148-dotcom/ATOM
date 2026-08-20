-- Permit Q10 options volatility in the immutable directional forecast ledger.
ALTER TABLE forecasts
    DROP CONSTRAINT forecasts_quant_id_check,
    ADD CONSTRAINT forecasts_quant_id_check CHECK (
        quant_id IN (
            'q1_momentum',
            'q2_mean_reversion',
            'q4_stat_arb',
            'q5_microstructure',
            'q6_volume_liquidity',
            'q7_relative_value',
            'q8_cross_asset',
            'q9_factor',
            'q10_options_vol',
            'q11_regime',
            'q12_event_session'
        )
    );
