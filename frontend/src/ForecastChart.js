// frontend/src/ForecastChart.js

import React, { useState, useEffect } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler, // Needed for filling area between lines
} from 'chart.js';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler
);

const API_BASE_URL = 'http://127.0.0.1:8000';

function ForecastChart({ nodeName }) {
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!nodeName) {
      setChartData(null);
      return;
    }

    const fetchForecast = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/suppliers/${nodeName}/forecast`);
        if (!response.ok) {
          const errData = await response.json();
          throw new Error(errData.detail || `HTTP error! status: ${response.status}`);
        }
        const forecastData = await response.json();

        // Format data for Chart.js
        const labels = forecastData.map(d => new Date(d.ds).toLocaleDateString());
        const data = {
          labels,
          datasets: [
            {
              label: 'Forecasted Risk',
              data: forecastData.map(d => d.yhat),
              borderColor: 'rgb(53, 162, 235)',
              backgroundColor: 'rgba(53, 162, 235, 0.5)',
              tension: 0.1,
            },
            {
              label: 'Confidence Interval',
              data: forecastData.map(d => [d.yhat_lower, d.yhat_upper]),
              backgroundColor: 'rgba(53, 162, 235, 0.2)',
              borderColor: 'transparent',
              fill: '-1', // Fill to the previous dataset
              pointRadius: 0,
            },
          ],
        };
        setChartData(data);
      } catch (e) {
        console.error("Error fetching forecast:", e);
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };

    fetchForecast();
  }, [nodeName]);

  if (!nodeName) {
    return <p style={{textAlign: 'center', color: '#888'}}>Select a supplier node to view its risk forecast.</p>;
  }
  
  if (loading) return <p>Loading forecast...</p>;
  if (error) return <p style={{ color: 'red' }}>Error loading forecast: {error}</p>;
  if (!chartData) return null;

  const options = {
    responsive: true,
    plugins: {
      legend: { position: 'top' },
      title: { display: true, text: `14-Day Risk Score Forecast for ${nodeName}` },
    },
    scales: {
        y: { beginAtZero: true, title: { display: true, text: 'Aggregated Daily Risk Score' } }
    }
  };

  return <Line options={options} data={chartData} />;
}

export default ForecastChart;
