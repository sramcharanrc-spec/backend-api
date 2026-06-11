from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text

from app.models.base import Base


class PayerRule(Base):
    __tablename__ = "payer_rules"

    id = Column(Integer, primary_key=True, index=True)
    payer_name = Column(String, nullable=False, index=True)
    rule_name = Column(String, nullable=False)
    rule_type = Column(String, nullable=False, index=True)
    condition = Column(JSON, default=dict)
    action = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class DecisionLog(Base):
    __tablename__ = "decision_logs"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, nullable=False, index=True)
    agent = Column(String, nullable=False, index=True)
    input_payload = Column(JSON, default=dict)
    rules_evaluated = Column(JSON, default=list)
    decision = Column(String, nullable=False, index=True)
    reasoning = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class ClaimMetric(Base):
    __tablename__ = "claim_metrics"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, nullable=False, index=True)
    metric_name = Column(String, nullable=False, index=True)
    metric_value = Column(Float, default=0.0)
    dimensions = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AgentEventRecord(Base):
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    agent = Column(String, nullable=False, index=True)
    stage = Column(String, index=True)
    status = Column(String, nullable=False, index=True)
    progress = Column(Float)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration = Column(Float)
    input_count = Column(Integer)
    output_count = Column(Integer)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
