# Street Food Shop Management System

## 1. Project Overview

### Project Name

Street Food Shop Management System

### Objective

To create a mobile-friendly web application that allows daily sales entry, automatic Excel storage, sales tracking, weather-based business analysis, and future AI-based sales prediction.

The system should be simple enough for daily shop operations while collecting high-quality data for future machine learning models.

---

## 2. Business Type

Street Food Shop

Products:

* Chicken Pakoda
* Leg Piece
* Wings
* Liver
* Soup (Dine-In / Parcel)
* Fish1
* Fish2
* Gravy

---

## 3. Main Goals

### Daily Operations

* Record product sales quickly.
* Automatically calculate quantities and amounts.
* Store all sales in Excel files.

### Management

* Track daily revenue.
* Track orders and items sold.
* Monitor weather impact on sales.
* Record special events and holidays.

### Future AI Goals

* Sales prediction.
* Best-selling product prediction.
* Weather impact analysis.
* Demand forecasting.
* Business performance analytics.

---

## 4. System Architecture

Mobile Browser
↓
Flask Frontend
↓
Python Backend
↓
Excel Storage
↓
Analytics & AI Models

---

## 5. Application Pages

### Page 1 - Dashboard

Purpose:
Daily shop overview.

Features:

* Date
* Day
* Weather
* Temperature
* Total Revenue
* Total Orders
* Total Items Sold
* Best Selling Product
* Start Shop Button
* Today Sales Button
* Close Shop Button

---

### Page 2 - Sales Entry

Purpose:
Quick sales recording.

Features:

* Revenue Summary
* Orders Summary
* Items Summary
* Product Search
* Product Cards
* Enter Sale Button

Product Types:

#### Weight-Based Products

Chicken Pakoda
Liver

Workflow:
Amount → Auto Weight Calculation → Save

Example:
₹100 → 200g

#### Piece-Based Products

Leg
Wings
Fish1
Fish2
Gravy

Workflow:
Quantity → Auto Amount Calculation → Save

Example:
3 × ₹50 = ₹150

#### Variant Product

Soup

Options:

* Dine-In = ₹30
* Parcel = ₹35

Workflow:
Variant + Quantity → Auto Amount

---

### Page 3 - Today Sales Management

Purpose:
Manage today's sales.

Features:

* Revenue Summary
* Orders Summary
* Items Summary
* Sales List
* Edit Sale
* Delete Sale
* Close Shop

---

## 6. Excel Database Structure

### product_master.xlsx

Columns:

* Product_Name
* Sale_Type
* Unit
* Unit_Price
* Variant

Purpose:
Master product configuration.

---

### sales.xlsx

Columns:

* Sale_ID
* Date
* Time
* Product_Name
* Sale_Type
* Variant
* Quantity
* Unit
* Unit_Price
* Total_Amount
* Weather
* Customer_Type
* Special_Event

Purpose:
Stores every sale transaction.

---

### daily_summary.xlsx

Columns:

* Date
* Day
* Open_Time
* Close_Time
* Weather
* Temperature
* Special_Event
* Is_Holiday
* Total_Sales_Amount
* Total_Transactions
* Total_Items_Sold
* Best_Selling_Product
* Notes

Purpose:
Stores one summary record per day.

---

## 7. Weather Integration

Source:
Weather API

Data Stored:

* Weather
* Temperature

Usage:

* Sales trend analysis
* Future AI prediction

---

## 8. Sales Calculations

### Weight Products

Chicken Pakoda

100g = ₹50
250g = ₹120
500g = ₹240

Example:
Amount ₹100
→ Weight 200g

---

### Piece Products

Leg Piece

1 Piece = ₹50

Example:
Qty 3
→ ₹150

---

### Soup

Dine-In = ₹30
Parcel = ₹35

Example:
Parcel × 2
→ ₹70

---

## 9. Backend Functions

### Shop Operations

open_shop()

close_shop()

get_shop_status()

update_daily_summary()

---

### Sales Operations

add_sale()

edit_sale()

delete_sale()

view_today_sales()

---

### Dashboard Operations

get_dashboard_data()

get_weather_data()

---

## 10. Future Analytics

### Sales Analysis

* Daily Revenue
* Weekly Revenue
* Monthly Revenue

### Product Analysis

* Best Selling Product
* Worst Selling Product

### Weather Analysis

* Weather vs Revenue
* Weather vs Product Demand

---

## 11. Future Machine Learning

After collecting 3+ months of data:

### Clustering

* High Demand Days
* Medium Demand Days
* Low Demand Days

### Prediction

* Revenue Forecasting
* Product Demand Forecasting

### Recommendation Engine

* Suggested Preparation Quantity
* Suggested Product Focus

---

## 12. Future Mobile App

Current:
Flask Web Application

Future:

* Android App
* Real-Time Sync
* Notification System
* Cloud Backup

---

## 13. Current Project Status

Completed:

* Backend Excel System
* Product Master
* Sales Logic
* Edit/Delete Functions
* Daily Summary
* Dashboard UI
* Sales Entry UI
* Today Sales UI

In Progress:

* Frontend Integration
* Excel Connection
* Dynamic Sales Display

Planned:

* Analytics Dashboard
* AI Prediction Module
* Android Deployment
