"""
Report generator for insolation and KEO calculation results.
Generates formatted reports with diagrams, tables, and compliance information.
"""

from typing import List, Dict, Optional
from datetime import date
from pathlib import Path
import yaml

from models.calculation_result import BuildingCalculationResult, RoomCalculationResult
from models.building import Building
from .report_enhancements import ReportSettings, ReportTextEditor, PlanOrganizer


class ReportGenerator:
    """Generates formatted reports from calculation results."""
    
    def __init__(self, config_path: Optional[str] = None, report_settings: Optional[ReportSettings] = None):
        """
        Initialize report generator.
        
        Args:
            config_path: Path to configuration file
            report_settings: Optional report settings (plan selection, scales, etc.)
        """
        self.config = self._load_config(config_path)
        self.output_format = self.config.get('reports', {}).get('format', 'pdf')
        self.include_diagrams = self.config.get('reports', {}).get('include_diagrams', True)
        self.include_stamps = self.config.get('reports', {}).get('include_stamps', True)
        self.report_settings = report_settings or ReportSettings()
        self.text_editor = ReportTextEditor()
        self.plan_organizer = PlanOrganizer()
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from file."""
        if config_path is None:
            config_path = 'config.yaml'
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}
    
    def generate_report(
        self,
        building_result: BuildingCalculationResult,
        output_path: str,
        building: Optional[Building] = None
    ) -> str:
        """
        Generate complete report for building calculation results.
        
        Args:
            building_result: Building calculation results
            output_path: Path to save report
            building: Building model (optional, for additional context)
        
        Returns:
            Path to generated report file
        """
        if self.output_format == 'pdf':
            return self._generate_pdf_report(building_result, output_path, building)
        elif self.output_format == 'html':
            return self._generate_html_report(building_result, output_path, building)
        elif self.output_format == 'docx':
            return self._generate_docx_report(building_result, output_path, building)
        else:
            raise ValueError(f"Unsupported report format: {self.output_format}")
    
    def _generate_pdf_report(
        self,
        building_result: BuildingCalculationResult,
        output_path: str,
        building: Optional[Building]
    ) -> str:
        """Generate PDF report."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        
        # Create PDF document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )
        
        # Container for the 'Flowable' objects
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        title = Paragraph("Расчет инсоляции и КЕО", title_style)
        elements.append(title)
        elements.append(Spacer(1, 12))
        
        # Building information
        building_info = [
            ['Здание:', building_result.building_name],
            ['Дата расчета:', building_result.calculation_date.strftime('%d.%m.%Y') if building_result.calculation_date else 'N/A'],
        ]
        if building:
            building_info.append(['Количество помещений:', str(building.get_total_rooms())])
        
        info_table = Table(building_info, colWidths=[60*mm, 120*mm])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 20))
        
        # Summary
        summary = building_result.get_compliance_summary()
        summary_text = f"""
        <b>Сводка по зданию:</b><br/>
        Всего помещений: {summary['total_rooms']}<br/>
        Соответствующих требованиям: {summary['compliant_rooms']}<br/>
        Не соответствующих требованиям: {summary['non_compliant_rooms']}<br/>
        Процент соответствия: {summary['compliance_rate']*100:.1f}%
        """
        elements.append(Paragraph(summary_text, styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Room results - organized by floor
        elements.append(Paragraph("<b>Результаты по помещениям:</b>", styles['Heading2']))
        elements.append(Spacer(1, 12))
        
        # Organize room results by floor (prevent chaotic sequence)
        room_results_organized = self._organize_room_results(building_result.room_results)
        
        for room_result in room_results_organized:
            # Room header
            room_header = f"Помещение: {room_result.room_name} (ID: {room_result.room_id})"
            elements.append(Paragraph(room_header, styles['Heading3']))
            
            # Insolation results
            if room_result.insolation_result:
                ins = room_result.insolation_result
                ins_text = f"""
                <b>Инсоляция:</b><br/>
                Продолжительность: {ins.duration_formatted}<br/>
                Соответствие требованиям: {'Да' if ins.meets_requirement else 'Нет'}
                """
                elements.append(Paragraph(ins_text, styles['Normal']))
            
            # KEO results
            if room_result.keo_result:
                keo = room_result.keo_result
                keo_text = f"""
                <b>КЕО:</b><br/>
                Общий КЕО: {keo.keo_total:.2f}%<br/>
                Соответствие требованиям: {'Да' if keo.meets_requirement else 'Нет'}
                """
                elements.append(Paragraph(keo_text, styles['Normal']))
            
            # Compliance status
            status_color = colors.green if room_result.is_compliant else colors.red
            status_text = f"<b>Статус:</b> {'Соответствует' if room_result.is_compliant else 'Не соответствует'}"
            status_para = Paragraph(status_text, styles['Normal'])
            elements.append(status_para)
            
            # Warnings
            if room_result.warnings:
                warnings_text = "<b>Предупреждения:</b><br/>" + "<br/>".join(room_result.warnings)
                elements.append(Paragraph(warnings_text, styles['Normal']))
            
            elements.append(Spacer(1, 20))
            elements.append(PageBreak())
        
        # Add custom text sections if edited
        if self.text_editor.custom_texts:
            elements.append(PageBreak())
            elements.append(Paragraph("<b>Дополнительная информация:</b>", styles['Heading2']))
            for section, text in self.text_editor.custom_texts.items():
                elements.append(Paragraph(f"<b>{section}:</b><br/>{text}", styles['Normal']))
                elements.append(Spacer(1, 12))
        
        # Add stamps if enabled
        if self.include_stamps and self.text_editor.get_all_stamps():
            elements.append(PageBreak())
            elements.append(Paragraph("<b>Подписи и печати:</b>", styles['Heading2']))
            elements.append(Spacer(1, 12))
            # Add stamp placeholders (can be filled with images)
            for stamp_type, stamp_data in self.text_editor.get_all_stamps().items():
                stamp_text = f"<b>{stamp_type}:</b><br/>"
                if 'name' in stamp_data:
                    stamp_text += f"Имя: {stamp_data['name']}<br/>"
                if 'date' in stamp_data:
                    stamp_text += f"Дата: {stamp_data['date']}<br/>"
                elements.append(Paragraph(stamp_text, styles['Normal']))
                elements.append(Spacer(1, 20))
        
        # Build PDF
        doc.build(elements)
        
        return output_path
    
    def _organize_room_results(self, room_results: List[RoomCalculationResult]) -> List[RoomCalculationResult]:
        """
        Organize room results by floor to prevent chaotic sequence.
        
        Args:
            room_results: List of room results
        
        Returns:
            Organized list (sorted by floor, then room ID)
        """
        # Extract floor numbers from room IDs or use default
        def get_floor_number(room_result: RoomCalculationResult) -> int:
            # Try to extract from room_id or use 0 as default
            try:
                # Common patterns: "Room_1F_1", "Floor1_Room1", etc.
                room_id_lower = room_result.room_id.lower()
                if 'floor' in room_id_lower or 'f' in room_id_lower:
                    # Extract number after 'floor' or 'f'
                    import re
                    match = re.search(r'(?:floor|f)[\s_-]*(\d+)', room_id_lower)
                    if match:
                        return int(match.group(1))
            except:
                pass
            return 0
        
        # Sort by floor number, then by room ID
        sorted_results = sorted(
            room_results,
            key=lambda r: (get_floor_number(r), r.room_id)
        )
        
        return sorted_results
    
    def _generate_html_report(
        self,
        building_result: BuildingCalculationResult,
        output_path: str,
        building: Optional[Building]
    ) -> str:
        """Generate HTML report."""
        html_content = f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <title>Расчет инсоляции и КЕО</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #1a1a1a; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .compliant {{ color: green; }}
                .non-compliant {{ color: red; }}
            </style>
        </head>
        <body>
            <h1>Расчет инсоляции и КЕО</h1>
            <h2>Здание: {building_result.building_name}</h2>
            <p>Дата расчета: {building_result.calculation_date.strftime('%d.%m.%Y') if building_result.calculation_date else 'N/A'}</p>
        """
        
        # Add room results
        for room_result in building_result.room_results:
            html_content += f"""
            <h3>Помещение: {room_result.room_name}</h3>
            <table>
                <tr>
                    <th>Параметр</th>
                    <th>Значение</th>
                </tr>
            """
            
            if room_result.insolation_result:
                ins = room_result.insolation_result
                html_content += f"""
                <tr>
                    <td>Инсоляция</td>
                    <td>{ins.duration_formatted}</td>
                </tr>
                <tr>
                    <td>Соответствие инсоляции</td>
                    <td class="{'compliant' if ins.meets_requirement else 'non-compliant'}">
                        {'Да' if ins.meets_requirement else 'Нет'}
                    </td>
                </tr>
                """
            
            if room_result.keo_result:
                keo = room_result.keo_result
                html_content += f"""
                <tr>
                    <td>КЕО</td>
                    <td>{keo.keo_total:.2f}%</td>
                </tr>
                <tr>
                    <td>Соответствие КЕО</td>
                    <td class="{'compliant' if keo.meets_requirement else 'non-compliant'}">
                        {'Да' if keo.meets_requirement else 'Нет'}
                    </td>
                </tr>
                """
            
            html_content += "</table>"
        
        html_content += """
        </body>
        </html>
        """
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path
    
    def _generate_docx_report(
        self,
        building_result: BuildingCalculationResult,
        output_path: str,
        building: Optional[Building]
    ) -> str:
        """Generate DOCX report."""
        # TODO: Implement DOCX generation using python-docx
        # For now, fall back to HTML
        return self._generate_html_report(building_result, output_path.replace('.docx', '.html'), building)

