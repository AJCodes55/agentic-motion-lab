import os
import zipfile
import requests
import pandas as pd
import openpyxl
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# 1. Define URLs for Jan and Feb 2026 Citi Bike data
urls = {
    "January": "https://s3.amazonaws.com/tripdata/202601-citibike-tripdata.csv.zip",
    "February": "https://s3.amazonaws.com/tripdata/202602-citibike-tripdata.csv.zip"
}

monthly_totals = {}
all_stations = []

print("Downloading and processing data from AWS S3 (this may take a moment)...")

for month_name, url in urls.items():
    zip_filename = f"{month_name}.zip"
    
    # Download zip file
    response = requests.get(url)
    if response.status_code == 200:
        with open(zip_filename, "wb") as f:
            f.write(response.content)
            
        # Extract and read CSV from zip
        with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
            csv_name = [name for name in zip_ref.namelist() if name.endswith('.csv') and not name.startswith('__MACOSX')][0]
            with zip_ref.open(csv_name) as csv_file:
                df = pd.read_csv(csv_file, low_memory=False)
        
        # Calculate Total Rides
        monthly_totals[month_name] = len(df)
        
        # Get start station counts
        station_col = 'start_station_name' if 'start_station_name' in df.columns else df.columns[3]
        top_stations = df[station_col].value_counts().reset_index()
        top_stations.columns = ['Station Name', 'Ride Count']
        top_stations['Month'] = month_name
        all_stations.append(top_stations)
        
        # Clean up temporary zip file
        os.remove(zip_filename)
    else:
        print(f"Failed to download {month_name} data. Status code: {response.status_code}")

# Combine stations data to find top 5 overall across both months
combined_stations = pd.concat(all_stations)
top_overall_stations = combined_stations.groupby('Station Name')['Ride Count'].sum().reset_index()
top_5_stations = top_overall_stations.sort_values(by='Ride Count', ascending=False).head(5)

# 2. Create Excel Workbook using openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Winter Summary"

# Ensure grid lines are visible
ws.views.sheetView[0].showGridLines = True

# Formatting styles
font_title = Font(name='Calibri', size=16, bold=True, color='1F4E78')
font_header = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
fill_header = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
font_bold = Font(name='Calibri', size=11, bold=True)
font_regular = Font(name='Calibri', size=11)
border_thin = Border(
    left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'),
    top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9')
)

# Sheet Title
ws['A1'] = "Citi Bike Winter 2026 Performance (Jan & Feb)"
ws['A1'].font = font_title
ws.merge_cells('A1:D1')

# --- Table 1: Monthly Ride Totals ---
ws['A3'] = "Month-over-Month Ride Totals"
ws['A3'].font = font_bold

headers_s1 = ["Month", "Total Rides"]
for col_num, header in enumerate(headers_s1, start=1):
    cell = ws.cell(row=4, column=col_num, value=header)
    cell.font = font_header
    cell.fill = fill_header
    cell.alignment = Alignment(horizontal='center', vertical='center')

row_idx = 5
for month, count in monthly_totals.items():
    c1 = ws.cell(row=row_idx, column=1, value=month)
    c2 = ws.cell(row=row_idx, column=2, value=count)
    c1.font = font_regular
    c2.font = font_regular
    c2.number_format = '#,##0'
    c1.border = border_thin
    c2.border = border_thin
    row_idx += 1

# --- Table 2: Top 5 Start Stations ---
row_idx += 2 
ws.cell(row=row_idx, column=1, value="Top 5 Start Stations (Combined)").font = font_bold
row_idx += 1

headers_s2 = ["Rank", "Station Name", "Total Rides"]
for col_num, header in enumerate(headers_s2, start=1):
    cell = ws.cell(row=row_idx, column=col_num, value=header)
    cell.font = font_header
    cell.fill = fill_header
    cell.alignment = Alignment(horizontal='center', vertical='center')

row_idx += 1
rank = 1
for _, row in top_5_stations.iterrows():
    c1 = ws.cell(row=row_idx, column=1, value=rank)
    c2 = ws.cell(row=row_idx, column=2, value=row['Station Name'])
    c3 = ws.cell(row=row_idx, column=3, value=row['Ride Count'])
    
    c1.alignment = Alignment(horizontal='center', vertical='center')
    c2.alignment = Alignment(horizontal='left', vertical='center')
    c3.alignment = Alignment(horizontal='right', vertical='center')
    
    c1.font = font_regular
    c2.font = font_regular
    c3.font = font_regular
    c3.number_format = '#,##0'
    
    c1.border = border_thin
    c2.border = border_thin
    c3.border = border_thin
    
    rank += 1
    row_idx += 1

# --- Simple Column Chart ---
chart = BarChart()
chart.type = "col"
chart.style = 10
chart.title = "January vs. February Total Rides"
chart.y_axis.title = "Number of Rides"
chart.x_axis.title = "Month"

data_ref = Reference(ws, min_col=2, min_row=4, max_row=6)
cats_ref = Reference(ws, min_col=1, min_row=5, max_row=6)

chart.add_data(data_ref, titles_from_data=True)
chart.set_categories(cats_ref)
chart.legend = None

# Place chart next to the tables
ws.add_chart(chart, "E4")

# Auto-adjust column widths for readability
for col in ws.columns:
    max_len = max(len(str(cell.value or '')) for cell in col)
    col_letter = openpyxl.utils.get_column_letter(col[0].column)
    ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

# Save output file
output_filename = "Citi_Bike_Winter_2026_Basic_Report.xlsx"
wb.save(output_filename)
print(f"Done! Workbook successfully saved as '{output_filename}'")