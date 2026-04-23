// frontend/src/HybridForecastChart.js
/**
 * Enhanced forecast chart that shows:
 * - Total hybrid forecast
 * - News-based predictions (upcoming hurricanes, strikes, etc.)
 * - Historical trend baseline
 * 
 * This enables visualization of HOW MUCH of the forecast is driven by
 * news about upcoming events vs historical patterns.
 */

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
  Filler,
} from 'chart.js';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler
);

const API_BASE_URL = 'http://127.0.0.1:8000';

function HybridForecastChart({ nodeName }) {
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [forecastStats, setForecastStats] = useState(null);

  useEffect(() => {
    if (!nodeName) {
      setChartData(null);
      return;
    }

    const fetchHybridForecast = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/suppliers/${nodeName}/hybrid_forecast`);
        if (!response.ok) {
          const errData = await response.json();
          throw new Error(errData.detail || `HTTP error! status: ${response.status}`);
        }
        const forecastData = await response.json();

        // Calculate statistics about the forecast
        const totalRisk = forecastData.reduce((sum, d) => sum + d.yhat, 0);
        const newsContribution = forecastData.reduce((sum, d) => sum + d.news_contribution, 0);
        const historicalContribution = forecastData.reduce((sum, d) => sum + d.historical_contribution, 0);
        const daysWithNewsSignals = forecastData.filter(d => d.news_contribution > 0).length;
        
        const newsPercentage = totalRisk > 0 
          ? ((newsContribution / (newsContribution + historicalContribution)) * 100).toFixed(1)
          : 0;

        setForecastStats({
          totalRisk: totalRisk.toFixed(1),
          newsPercentage,
          daysWithNewsSignals,
          peakRiskDate: forecastData.reduce((max, d) => d.yhat > max.yhat ? d : max, forecastData[0])
        });

        // Format data for Chart.js with THREE datasets
        const labels = forecastData.map(d => new Date(d.ds).toLocaleDateString());
        const data = {
          labels,
          datasets: [
            {
              label: 'Total Forecasted Risk',
              data: forecastData.map(d => d.yhat),
              borderColor: 'rgb(255, 99, 132)',
              backgroundColor: 'rgba(255, 99, 132, 0.5)',
              tension: 0.3,
              borderWidth: 3,
              fill: false,
            },
            {
              label: 'News-Based Prediction (Upcoming Events)',
              data: forecastData.map(d => d.news_contribution),
              borderColor: 'rgb(54, 162, 235)',
              backgroundColor: 'rgba(54, 162, 235, 0.3)',
              tension: 0.1,
              borderWidth: 2,
              fill: 'origin',
            },
            {
              label: 'Historical Trend Baseline',
              data: forecastData.map(d => d.historical_contribution),
              borderColor: 'rgb(75, 192, 192)',
              backgroundColor: 'rgba(75, 192, 192, 0.3)',
              tension: 0.3,
              borderWidth: 2,
              borderDash: [5, 5],
              fill: 'origin',
            },
            {
              label: 'Confidence Interval',
              data: forecastData.map(d => [d.yhat_lower, d.yhat_upper]),
              backgroundColor: 'rgba(255, 99, 132, 0.1)',
              borderColor: 'transparent',
              fill: '-3', // Fill to the first dataset
              pointRadius: 0,
            },
          ],
        };
        setChartData(data);
      } catch (e) {
        console.error("Error fetching hybrid forecast:", e);
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };

    fetchHybridForecast();
  }, [nodeName]);

  if (!nodeName) {
    return (
      <div style={{textAlign: 'center', color: '#888', padding: '20px'}}>
        <p>Select a supplier node to view its predictive risk forecast.</p>
        <p style={{fontSize: '0.9em', marginTop: '10px'}}>
          🔮 This forecast analyzes news about <strong>upcoming events</strong> like hurricanes, 
          strikes, and regulatory changes.
        </p>
      </div>
    );
  }
  
  if (loading) return <p>Loading hybrid forecast...</p>;
  
  if (error) {
    return (
      <div style={{ color: '#d9534f', padding: '15px' }}>
        <p><strong>Error loading hybrid forecast:</strong></p>
        <p>{error}</p>
        <p style={{fontSize: '0.85em', marginTop: '10px'}}>
          💡 Tip: Run <code>python src/predictive_forecasting.py</code> to generate hybrid forecasts.
        </p>
      </div>
    );
  }
  
  if (!chartData) return null;

  const options = {
    responsive: true,
    plugins: {
      legend: { 
        position: 'top',
        labels: {
          usePointStyle: true,
          padding: 15
        }
      },
      title: { 
        display: true, 
        text: `14-Day Hybrid Risk Forecast for ${nodeName}`,
        font: { size: 16 }
      },
      tooltip: {
        callbacks: {
          footer: function(tooltipItems) {
            const index = tooltipItems[0].dataIndex;
            const forecastPoint = tooltipItems[0].chart.config._config.data.datasets[0].data[index];
            return `Method: ${tooltipItems[0].chart.config._config.method || 'hybrid'}`;
          }
        }
      }
    },
    scales: {
      y: { 
        beginAtZero: true, 
        title: { display: true, text: 'Aggregated Daily Risk Score' },
        ticks: {
          callback: function(value) {
            return value.toFixed(1);
          }
        }
      },
      x: {
        title: { display: true, text: 'Date' }
      }
    },
    interaction: {
      mode: 'index',
      intersect: false,
    }
  };

  return (
    <div>
      <Line options={options} data={chartData} />
      
      {forecastStats && (
        <div style={{
          marginTop: '15px',
          padding: '15px',
          backgroundColor: '#f8f9fa',
          borderRadius: '5px',
          fontSize: '0.9em'
        }}>
          <h4 style={{marginTop: 0}}>📊 Forecast Analysis</h4>
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px'}}>
            <div>
              <strong>Total Forecasted Risk:</strong> {forecastStats.totalRisk}
            </div>
            <div>
              <strong>News-Driven:</strong> {forecastStats.newsPercentage}%
            </div>
            <div>
              <strong>Days with News Signals:</strong> {forecastStats.daysWithNewsSignals}
            </div>
            <div>
              <strong>Peak Risk Date:</strong> {new Date(forecastStats.peakRiskDate.ds).toLocaleDateString()}
            </div>
          </div>
          
          {forecastStats.newsPercentage > 60 && (
            <div style={{
              marginTop: '10px',
              padding: '10px',
              backgroundColor: '#fff3cd',
              borderLeft: '4px solid #ffc107',
              borderRadius: '3px'
            }}>
              ⚠️ <strong>High News Impact:</strong> This forecast is heavily influenced by 
              news about upcoming events. Review recent articles for details.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default HybridForecastChart;

