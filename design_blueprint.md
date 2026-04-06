# AI Symptom Checker Demo - UI/UX Design Blueprint

## Overview
This blueprint outlines a premium, trustworthy UI/UX design for the "AI Symptom Checker Demo" web application. The design emphasizes safety, calmness, and clinical modernity while maintaining an elegant, startup-polished aesthetic. All designs prioritize user trust, ethical considerations, and clear communication that this is not a medical diagnosis.

**Prominent Disclaimer:** Throughout the application, prominently display:  
*"Bu tibbiy tashxis emas. Bu faqat umumiy AI tavsiyasi."*  
(This is not a medical diagnosis. This is only general AI advice.)

## Color Palette
- **Primary Background:** Pure white (#FFFFFF) or very light gray (#F8F9FA) for cleanliness and approachability
- **Accent Colors:** Soft teal (#4A90E2) for primary actions, gentle blue (#7B68EE) for secondary elements
- **Risk Level Colors:**
  - Low Risk: Soft green (#A8DADC)
  - Medium Risk: Warm yellow (#F4A261)
  - High Risk: Coral orange (#E76F51)
  - Emergency: Deep red (#D62828)
- **Text Colors:** Dark gray (#2D3748) for primary text, medium gray (#718096) for secondary
- **Borders/Shadows:** Light gray (#E2E8F0) for subtle shadows and borders

## Typography
- **Primary Font:** Inter (modern, clean, highly legible) - weights: 400, 500, 600, 700
- **Secondary Font:** Source Sans Pro for body text (humanist sans-serif for warmth)
- **Hierarchy:**
  - H1: 48px, 700 weight, line-height 1.2
  - H2: 36px, 600 weight, line-height 1.3
  - H3: 24px, 600 weight, line-height 1.4
  - Body: 16px, 400 weight, line-height 1.6
  - Small: 14px, 400 weight, line-height 1.5

## Component System

### Cards
- **Style:** Rounded corners (12px radius), subtle box-shadow (0 4px 6px rgba(0,0,0,0.07)), white background
- **Padding:** 24px internal, 16px between elements
- **Variants:** Trust cards (with icons), form cards, result cards

### Buttons
- **Primary CTA:** Soft teal background (#4A90E2), white text, 16px padding, 8px border radius, hover: darker teal (#357ABD)
- **Secondary:** Outline style with teal border, transparent background, hover: light teal fill
- **Emergency:** Deep red background for urgent actions, with clear warning icon

### Icons
- **Style:** Modern, minimalist icons from Feather Icons or Heroicons
- **Medical Theme:** Subtle illustrations (e.g., abstract DNA helix, gentle pulse waves) rather than realistic medical imagery

## Layout Hierarchy
- **Above the Fold:** Hero section with clear value proposition, prominent disclaimer, and call-to-action
- **Visual Priority:** Hero > Trust indicators > How it works > Form/Results
- **Spacing:** Generous whitespace (24px minimum between sections), 64px section padding
- **Grid:** 12-column responsive grid, max-width 1200px centered

## Page Structures

### Landing Page
1. **Hero Section:** Full-width, centered content
   - Headline: "AI Symptom Checker Demo"
   - Subheadline: Brief value prop
   - Prominent disclaimer
   - Primary CTA: "Start Symptom Check"
   - Background: Subtle gradient or soft illustration

2. **Trust/Value Cards:** 3-column grid
   - Card 1: AI-Powered Guidance
   - Card 2: Privacy-Focused
   - Card 3: Expert-Backed

3. **How It Works:** Step-by-step illustration
   - Step 1: Enter Symptoms
   - Step 2: AI Analysis
   - Step 3: Get Guidance

4. **Symptom Form Area:** Embedded form for quick start

5. **Disclaimer Section:** Full-width, emphasized

6. **FAQ:** Accordion-style

7. **Footer:** Links, copyright, additional disclaimer

### App Page (Symptom Input)
- **Header:** App title, back button, progress indicator
- **Form Card:** Centered, multi-step form
  - Symptoms input (textarea with suggestions)
  - Age slider
  - Gender (optional radio)
  - Duration dropdown
  - Submit button
- **Sidebar:** Tips and reassurance

### Result Page
- **Header:** Clear result title
- **Risk Level Banner:** Color-coded banner with icon
- **Result Cards:**
  - General Risk Level
  - Recommended Specialist
  - General Advice
  - Emergency Warning (if applicable)
- **Disclaimer:** Prominently placed
- **Actions:** "Check Another Symptom", "Learn More"

## Mobile Responsiveness
- **Breakpoint Strategy:** Desktop (>1024px), Tablet (768-1023px), Mobile (<768px)
- **Mobile First:** Single-column layout, stacked cards, touch-friendly buttons (44px minimum)
- **Touch Interactions:** Swipe gestures for form steps, tap-to-expand for results
- **Typography Scaling:** Responsive font sizes, minimum 16px for readability

## Premium Medical-Tech Visual Direction
- **Illustrations:** Soft, abstract medical-tech motifs (circuit patterns with organic curves, gentle data visualizations)
- **Animations:** Subtle micro-interactions (button hover states, form transitions)
- **Imagery:** Avoid stock photos; use custom illustrations showing diverse, inclusive representations
- **Trust Elements:** Certification badges, privacy icons, expert endorsements

## Implementation Suggestions for Flask Templates

### Base Template (base.html)
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}AI Symptom Checker Demo{% endblock %}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/styles.css') }}">
</head>
<body>
    {% block content %}{% endblock %}
    <script src="{{ url_for('static', filename='js/app.js') }}"></script>
</body>
</html>
```

### Landing Page (index.html)
- Hero: Full-height section with centered content
- Cards: Jinja loops for trust cards
- Form: Include symptom form component

### App Page (app.html)
- Form: Multi-step with JavaScript for validation
- Progress: Visual progress bar

### Result Page (result.html)
- Dynamic content: Jinja variables for results
- Color coding: CSS classes based on risk level

## Section-by-Section Visual Rationale

### Hero Section
**Design:** Large, centered headline with soft background illustration. Prominent CTA button.  
**Trust & Usability:** Immediately communicates the product's purpose. The disclaimer is visible without scrolling, building immediate trust. Clear CTA reduces friction for first-time users.

### Trust/Value Cards
**Design:** Three clean cards with icons and short descriptions.  
**Trust & Usability:** Social proof through icons and concise benefits. Builds credibility before user commitment. Icons provide visual scanning cues.

### How It Works
**Design:** Numbered steps with illustrations.  
**Trust & Usability:** Reduces anxiety by setting expectations. Visual flow guides users through the process, increasing confidence in the system.

### Symptom Form Area
**Design:** Clean card with labeled inputs, validation feedback.  
**Trust & Usability:** Clear labels and optional fields reduce cognitive load. Real-time validation prevents errors, enhancing user confidence.

### Result Display
**Design:** Color-coded risk levels, card-based layout.  
**Trust & Usability:** Visual hierarchy emphasizes important information. Color coding provides instant understanding of risk levels.

### Risk Level Color System
**Design:** Consistent color application across all risk indicators.  
**Trust & Usability:** Universal color language (green=safe, red=danger) ensures intuitive understanding. Consistent application builds familiarity.

### Disclaimer Section
**Design:** Bold typography, full-width placement.  
**Trust & Usability:** Prominent placement ensures legal and ethical compliance. Repetition reinforces the non-diagnostic nature.

### FAQ
**Design:** Expandable accordion.  
**Trust & Usability:** Addresses common concerns proactively. Expandable format saves space while providing depth.

### Footer
**Design:** Minimal links and copyright.  
**Trust & Usability:** Provides necessary legal information without overwhelming. Consistent branding maintains trust.

This blueprint ensures a premium, trustworthy experience that prioritizes user safety and ethical design principles.