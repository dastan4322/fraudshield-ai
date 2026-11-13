from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart

def make_pdf(rows, bundle, model_id, threshold):
    buffer = BytesIO()
    styles=getSampleStyleSheet()
    story=[Paragraph("FraudShield AI — Investigation report",styles["Title"]),
           Paragraph(datetime.now(timezone.utc).isoformat(),styles["Normal"]),Spacer(1,16)]
    summary=[["Model",escape(model_id)],["Version",escape(bundle["version"])],["Source",escape(bundle["source"])],
             ["Transactions",str(len(rows))],["Flagged",str(sum(r["prediction"] for r in rows))],["Review threshold",str(threshold)]]
    story.append(Table(summary,colWidths=[150,330]))
    story.append(Spacer(1,20))
    chart=VerticalBarChart()
    chart.x=40;chart.y=25;chart.width=400;chart.height=150
    chart.data=[[sum(r["risk_category"]==c for r in rows) for c in ["low","medium","high"]]]
    chart.categoryAxis.categoryNames=["Low","Medium","High"]
    chart.valueAxis.valueMin=0
    chart.bars[0].fillColor=colors.HexColor("#149b8e")
    drawing=Drawing(480,200);drawing.add(chart);story.append(drawing)
    story.append(Paragraph("Held-out training evaluation (not necessarily the uploaded dataset)",styles["Heading2"]))
    metric_rows=[["Metric","Value"]]+[[k,str(round(v,4))] for k,v in bundle["metrics"].items() if isinstance(v,(int,float))]
    metric_rows += [["Confusion matrix",str(bundle["metrics"]["confusion_matrix"])]]
    table=Table(metric_rows,colWidths=[220,260]);table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.lightgrey)]))
    story.append(table)
    if "is_fraud" in rows[0] and set(r["is_fraud"] for r in rows).issubset({0,1}):
        from sklearn.metrics import confusion_matrix
        actual=confusion_matrix([r["is_fraud"] for r in rows],[r["prediction"] for r in rows],labels=[0,1]).tolist()
        story.append(Paragraph("Uploaded label confusion matrix: "+escape(str(actual)),styles["Normal"]))
    story += [Spacer(1,20),Paragraph("Limitations and recommendations",styles["Heading2"]),
              Paragraph("Scores support manual investigation and do not prove fraud. Prioritize flagged cases, verify source information, and document review decisions. Lower thresholds generally increase workload. Synthetic models are not validated on real financial data. No regulated banking certification is claimed.",styles["Normal"])]
    SimpleDocTemplate(buffer).build(story)
    return buffer.getvalue()
