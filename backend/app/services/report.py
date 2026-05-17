"""월말 회계 리포트 (plan_phase4.6)

§4.2가 확정한 정산서 데이터를 한 달 단위로 모아 회계용 CSV로 만든다.
금액은 재계산하지 않고 정산서에 저장된 값을 그대로 인용한다.
"""
import csv
import io
from decimal import Decimal

from sqlmodel import Session, select

from app.models.domain import Branch, Settlement, SettlementItem

# 정산 상태 한글 표기
_STATUS_LABEL = {
    "DRAFT": "작성", "REVIEW": "검토중", "APPROVED": "승인",
    "PAID": "지급완료", "INVOICED": "계산서발행", "HOLD": "보류",
}

_HEADER = [
    "지사명", "정산기간", "정산상태", "건수", "매출(VAT포함)",
    "공급가액", "부가세", "수수료율(%)", "본사수수료", "환불차감", "지사지급액",
]


def monthly_report_filename(year: int, month: int) -> str:
    return f"WhiteOn_정산리포트_{year:04d}-{month:02d}.csv"


def build_monthly_csv(session: Session, year: int, month: int) -> str:
    """선택한 연·월에 마감(period_end)된 정산서를 모아 CSV 문자열을 만든다.

    맨 끝에 전 지사 합계 행을 붙인다. 반환 문자열은 UTF-8 BOM으로 시작해
    한글 Excel에서 바로 열린다.
    """
    settlements = session.exec(
        select(Settlement).order_by(Settlement.branch_id, Settlement.period_start)
    ).all()
    # period_end가 해당 연·월인 정산서만
    rows = [s for s in settlements if s.period_end.year == year and s.period_end.month == month]

    branch_names = {b.id: b.name for b in session.exec(select(Branch)).all()}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_HEADER)

    total = {k: Decimal("0") for k in ("gross", "supply", "vat", "hq", "refund", "net")}
    total_count = 0

    for s in rows:
        item_count = len(session.exec(
            select(SettlementItem).where(SettlementItem.settlement_id == s.id)
        ).all())
        supply = Decimal(s.gross_amount) - Decimal(s.vat_amount)
        writer.writerow([
            branch_names.get(s.branch_id, "(알 수 없음)"),
            f"{s.period_start} ~ {s.period_end}",
            _STATUS_LABEL.get(s.status, s.status),
            item_count,
            int(s.gross_amount),
            int(supply),
            int(s.vat_amount),
            f"{Decimal(s.commission_rate):g}",
            int(s.hq_commission),
            int(s.refund_offset),
            int(s.net_amount),
        ])
        total["gross"] += Decimal(s.gross_amount)
        total["supply"] += supply
        total["vat"] += Decimal(s.vat_amount)
        total["hq"] += Decimal(s.hq_commission)
        total["refund"] += Decimal(s.refund_offset)
        total["net"] += Decimal(s.net_amount)
        total_count += item_count

    writer.writerow([
        "합계", f"{year:04d}-{month:02d}", f"{len(rows)}건", total_count,
        int(total["gross"]), int(total["supply"]), int(total["vat"]),
        "", int(total["hq"]), int(total["refund"]), int(total["net"]),
    ])

    return "﻿" + buf.getvalue()
