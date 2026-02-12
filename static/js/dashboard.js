// static/js/dashboard.js

let myChart;
let currentMetric = 'distance_km';
let currentLabel = 'Distance (km)';

let currentModalData = [];

const typeColors = {
    'Ride': 'rgba(54, 162, 235, 0.7)',
    'Run': 'rgba(255, 99, 132, 0.7)',
    'Walk': 'rgba(75, 192, 192, 0.7)',
    'Hike': 'rgba(255, 159, 64, 0.7)',
    'VirtualRide': 'rgba(153, 102, 255, 0.7)'
};

function initChart() {
    const ctx = document.getElementById('distanceChart').getContext('2d');
    myChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    const index = elements[0].index;
                    const selectedMonthId = myChart.data.monthIds[index];
                    if (typeof fetchDailyData === "function") {
                        fetchDailyData(selectedMonthId);
                    }
                }
            }
        }
    });
}

function updateDashboard() {
    // 1. Get current filter states
    const rangeSelector = document.getElementById('rangeSelector');
    const selectedRange = rangeSelector ? parseInt(rangeSelector.value) : 0;
    const checkedBoxes = document.querySelectorAll('.type-checkbox:checked');
    const selectedTypes = Array.from(checkedBoxes).map(cb => cb.value);

    // 2. Simple Time Filter
    const timeFiltered = rawData.filter(item => {
        if (selectedRange === 0) return true; // All History
        
        const [year, month] = item.month_id.split('-').map(Number);
        const itemDate = new Date(year, month - 1, 1);
        
        let cutoffDate = new Date();
        cutoffDate.setMonth(cutoffDate.getMonth() - selectedRange);
        cutoffDate.setDate(1); // Start of that month
        
        return itemDate >= cutoffDate;
    });

    // 3. Type Filter
    const fullyFiltered = timeFiltered.filter(item => selectedTypes.includes(item.type));

    // 4. Update Totals (The Stats Boxes)
    document.getElementById('stat-count').innerText = fullyFiltered.reduce((sum, item) => sum + (Number(item.activities) || 0), 0).toLocaleString();
    const totalDistance = fullyFiltered.reduce((sum, item) => sum + (Number(item.distance_km) || 0), 0);

    document.getElementById('stat-distance').innerText = `${totalDistance.toLocaleString('de-DE', {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
    })} km`;
    
    const totalDuration = fullyFiltered.reduce((sum, item) => sum + (Number(item.duration_hours) || 0), 0);
    document.getElementById('stat-time').innerText = `${Math.floor(totalDuration)}h ${Math.round((totalDuration % 1) * 60)}m`;
    document.getElementById('stat-energy').innerText = `${Math.round(fullyFiltered.reduce((sum, item) => sum + (Number(item.total_kj) || 0), 0)).toLocaleString()} kJ`;

    // 5. Update Chart Labels and IDs
    const labels = [...new Set(timeFiltered.map(item => item.month_label))];
    const monthIds = [...new Set(timeFiltered.map(item => item.month_id))];

    // 6. Build Datasets
    const datasets = selectedTypes.map(type => ({
        label: type,
        data: labels.map(label => {
            const entry = timeFiltered.find(d => d.month_label === label && d.type === type);
            return entry ? (Number(entry[currentMetric]) || 0) : 0;
        }),
        backgroundColor: typeColors[type] || `rgba(100, 100, 100, 0.5)`,
        borderWidth: 1
    }));

    // 7. Push to Chart.js
    myChart.data.labels = labels;
    myChart.data.datasets = datasets;
    myChart.data.monthIds = monthIds; // Store for the click handler
    myChart.update();

    // Update Dropdown text
    const typeBtn = document.getElementById('typeDropdown');
    if (typeBtn) typeBtn.innerText = `Types (${selectedTypes.length})`;

    // update the table data:
    updateDataTable(timeFiltered, selectedTypes);
}

// Keeping your utility functions
function setMetric(key, label, color, event) {
    currentMetric = key;
    currentLabel = label;
    document.querySelectorAll('.metric-btn').forEach(b => b.classList.remove('active'));
    if (event && event.target) event.target.classList.add('active');
    updateDashboard();
}

function bulkSelect(shouldSelect, event) {
    if (event) event.stopPropagation();
    const checkboxes = document.querySelectorAll('.type-checkbox');
    checkboxes.forEach(cb => cb.checked = shouldSelect);
    updateDashboard();
}

async function fetchDailyData(monthId) {

    const exportBtn = document.getElementById('modalExportBtn');
    exportBtn.classList.add('d-none'); // Hide it while loading new data

    // 1. Show the modal using Bootstrap's API
    const modalElem = document.getElementById('activityModal');
    const modal = new bootstrap.Modal(modalElem);
    
    // Set title and show loading state
    document.getElementById('modalTitle').innerText = `Activities for ${monthId}`;
    document.getElementById('modalLoading').classList.remove('d-none');
    document.getElementById('modalTableContainer').classList.add('d-none');
    
    modal.show();

    try {
        // 2. Fetch data from your API
        const response = await fetch(`/api/activities/by-month/${monthId}`);
        const activities = await response.json();

        currentModalData = activities;

        const tbody = document.getElementById('activityListBody');
        tbody.innerHTML = ''; // Clear old rows

        // 3. Populate the table
        if (activities.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4">No activities found.</td></tr>';
        } else {
            activities.forEach(act => {
                const date = act.day_of_month; // We can just show the day since the month is in the title
                
                const totalHours = Number(act.duration_hours) || 0;
                const h = Math.floor(totalHours);
                const m = Math.round((totalHours % 1) * 60);
                const timeFormatted = `${h}:${m.toString().padStart(2, '0')}`;
                
                const dist = act.distance_km ? Number(act.distance_km).toFixed(1) : '0';
                const kj   = act.total_kj ? Math.round(act.total_kj).toLocaleString() : '0';
            
                const row = `
                    <tr>
                        <td class="ps-3 small text-muted">${date}</td>
                        <td class="fw-bold">${act.name}</td>
                        <td><span class="badge bg-light text-dark border">${act.type}</span></td>
                        <td class="text-end text-primary">${dist}</td>
                        <td class="text-end fw-mono">${timeFormatted}</td>
                        <td class="text-end pe-3 text-muted">${kj}</td>
                    </tr>
                `;
                tbody.insertAdjacentHTML('beforeend', row);
            });
        }

        // 4. Show the table, hide the spinner
        exportBtn.classList.remove('d-none');
        
        document.getElementById('modalLoading').classList.add('d-none');
        document.getElementById('modalTableContainer').classList.remove('d-none');


    } catch (error) {
        console.error('Error fetching activities:', error);
        document.getElementById('modalLoading').innerHTML = `<p class="text-danger p-3">Error loading data.</p>`;
    }
}

// Generic helper to turn any array of objects into a CSV
function downloadCSV(data, filename) {
    if (!data || data.length === 0) {
        alert("No data to export!");
        return;
    }

    // 1. Get headers dynamically from the keys of the first object
    const headers = Object.keys(data[0]);
    
    // 2. Map rows, handling commas/quotes in strings
    const rows = data.map(obj => {
        return headers.map(header => {
            let val = obj[header] === null ? '' : obj[header];
            // If it's a string with commas or quotes, wrap it in quotes
            if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
                val = `"${val.replace(/"/g, '""')}"`;
            }
            return val;
        }).join(",");
    });

    // 3. Combine and trigger download
    const csvContent = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    
    link.setAttribute("href", url);
    link.setAttribute("download", filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Now the specific buttons just pass the right data to the helper
function exportCurrentView() {
    const selectedRange = parseInt(document.getElementById('rangeSelector').value);
    const checkedBoxes = document.querySelectorAll('.type-checkbox:checked');
    const selectedTypes = Array.from(checkedBoxes).map(cb => cb.value);

    const filtered = rawData.filter(item => {
        const typeMatch = selectedTypes.includes(item.type);
        if (selectedRange === 0) return typeMatch;
        const [year, month] = item.month_id.split('-').map(Number);
        const itemDate = new Date(year, month - 1, 1);
        let cutoffDate = new Date();
        cutoffDate.setMonth(cutoffDate.getMonth() - selectedRange);
        cutoffDate.setDate(1);
        return typeMatch && itemDate >= cutoffDate;
    });

    downloadCSV(filtered, `Dashboard_View_${new Date().toISOString().split('T')[0]}.csv`);
}

function exportFullHistory() {
    downloadCSV(rawData, `Full_History_${new Date().toISOString().split('T')[0]}.csv`);
}

function exportModalActivities() {
    const monthTitle = document.getElementById('modalTitle').innerText
        .replace('Activities for ', '')
        .replace(/\s+/g, '_');
    
    downloadCSV(currentModalData, `Activities_${monthTitle}.csv`);
}

function updateDataTable(timeFiltered, selectedTypes) {
    const header = document.getElementById('tableHeader');
    const body = document.getElementById('tableBody');
    if (!header || !body) return;

    // 1. Setup Headers: Month + Selected Types + Total
    header.innerHTML = `<th class="ps-3">Month</th>` + 
        selectedTypes.map(t => `<th class="text-end small">${t}</th>`).join('') + 
        `<th class="text-end pe-3">Total</th>`;

    // 2. Get Unique Months (sorted newest first)
    const months = [...new Set(timeFiltered.map(item => item.month_label))].reverse();

    // 3. Generate Rows
    body.innerHTML = months.map(month => {
        let rowTotal = 0;
        
        const typeCells = selectedTypes.map(type => {
            const entry = timeFiltered.find(d => d.month_label === month && d.type === type);
            const val = entry ? (Number(entry[currentMetric]) || 0) : 0;
            rowTotal += val;
            
            // Format numbers: Distance/Energy get 1 decimal, Count gets 0
            const formattedVal = currentMetric === 'activities' ? val : val.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1});
            return `<td class="text-end text-muted">${val > 0 ? formattedVal : '-'}</td>`;
        }).join('');

        const formattedTotal = currentMetric === 'activities' ? rowTotal : rowTotal.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1});

        return `
            <tr>
                <td class="ps-3 fw-bold">${month}</td>
                ${typeCells}
                <td class="text-end pe-3 fw-bold bg-light">${formattedTotal}</td>
            </tr>`;
    }).join('');
}