---
title: "How to Display Content From Websites That Require a Login"
article_id: 360037391854
url: https://support.optisigns.com/hc/en-us/articles/360037391854-How-to-Display-Content-From-Websites-That-Require-a-Login
updated_at: 2026-10-16T17:01:33Z
---

# How to Display Content From Websites That Require a Login

Article URL: https://support.optisigns.com/hc/en-us/articles/360037391854-How-to-Display-Content-From-Websites-That-Require-a-Login

### In this article, we'll show the best way to put dashboards, boards and reports that sit behind a login on your digital signs with OptiSigns.

- [What You'll Need](#what-youll-need)
- [Option 1: Use a Dedicated App](#option-1-use-a-dedicated-app)
- [Option 2: Use Web Scripting](#option-2-use-web-scripting)
- [Option 3: Use Secured Dashboard](#option-3-use-secured-dashboard)
- [Websites With a Browser Sign-In Pop-up](#websites-with-a-browser-sign-in-pop-up)
- [Signing In on the Device](#signing-in-on-the-device)

A lot of the content worth showing on your screens sits behind a login: a project board in Jira, a sales dashboard in Salesforce, a report in Tableau or Power BI. OptiSigns gives you several ways to display it, and each one keeps your screens signed in without anyone standing at the device.

![Two kinds of login: a browser sign-in pop-up and a website login page](https://support.optisigns.com/hc/article_attachments/360103797493)

Here's how to decide what method to use:

If there is a dedicated OptiSigns app for the service, simply use that app. This is the easiest and most reliable option.

If there's no dedicated app, and the site has a normal login page, use [**Web Scripting**](./1500012522362-how-to-use-the-web-scripting-app.md). You'll need a Pro Plus plan for this.

If the login process requieres multi-factor authentication (MFA) on several screens, you have a mix of device types, or the report is slow to load, use [**Secured Dashboard**](./19589190970771-how-to-use-secured-dashboard-app.md).

The site asks for a username and password in a browser pop-up, use the [**Website app**](./360016382473-how-to-use-the-website-app-and-display-urls-on-optisigns.md) with the sign-in details in the URL.

Let's get started.

---

## What You'll Need

- An OptiSigns account. The plan you need depends on the option you use:
- Website app, and most dedicated apps - [**Standard Plan** or higher](https://www.optisigns.com/pricing)
- Web Scripting and Secured Dashboard - [**Pro Plus Plan** or higher](https://www.optisigns.com/pricing)
- An account on the website or service you want to display
- An [OptiSigns-enabled device](./360021855653-what-hardware-and-devices-are-supported.md)
- A screen, set up and paired with OptiSigns ([see our Getting Started guide](./18823504383891-optisigns-getting-started-guide.md))

---

## Option 1: Use a Dedicated App

OptiSigns has dedicated apps for many popular services. You sign in once in the OptiSigns portal, and the app keeps your screens up to date. Nobody needs to sign in on the device.

From the OptiSigns portal, go to **Files/Assets** and select **Apps**.

![OptiSigns Files/Assets page with the Apps button highlighted](https://support.optisigns.com/hc/article_attachments/56488921897491)

Search for the service you want to display. If it has a dedicated app, it will appear in the results.

![Add App dialog searched for Jira, with the Jira app card highlighted](https://support.optisigns.com/hc/article_attachments/56488885500819)

Dedicated apps include:

**Project and work management**

- [Jira](./360037416494-how-to-use-the-jira-app.md)
- [Trello](./360050244454-how-to-use-the-trello-app.md)
- [Asana](./1500002233221-how-to-use-the-asana-app.md)
- [Monday.com](./11032964830227-how-to-use-the-monday-com-app.md)
- [Notion](./5119724468371-how-to-use-the-notion-app.md)
- [Smartsheet](./8399990754195-how-to-display-a-smartsheet-report-on-optisigns.md)
- [Airtable](./9392587446675-how-to-use-airtable-with-optisigns.md)
- [Zendesk](./360060919453-how-to-use-the-zendesk-app.md)

**Dashboards and reports** (Pro Plus Plan or higher)

- [Salesforce](./55895814798739-how-to-display-salesforce-dashboards-and-reports-on-optisigns.md)
- [Tableau](./39250660729747-how-to-use-the-tableau-app.md)
- [Power BI](./360024859713-how-to-display-microsoft-power-bi-dashboards-reports-with-optisigns.md)
- [Looker Studio (Data Studio)](./360052088413-how-to-use-the-data-studio-app.md)
- [Grafana](./55447693635731-how-to-display-grafana-dashboards-on-optisigns.md)
- [Databricks](./53952018650515-how-to-display-databricks-dashboards-on-optisigns.md)
- [Snowflake](./53028011485715-how-to-display-a-snowflake-dashboard-with-optisigns.md)

**Microsoft 365 and Google**

- [SharePoint](./4414539282067-displaying-sharepoint-sites-on-optisigns.md)
- [Excel Online](./4529298306963-how-to-use-microsoft-excel-online-with-optisigns.md)
- [PowerPoint Online](./4414355658899-how-to-use-microsoft-powerpoint-with-optisigns.md)
- [Google Sheets](./360056977214-how-to-use-google-sheets-with-optisigns.md)

Follow the article for your app to set it up.

---

## Option 2: Use Web Scripting

If there's no dedicated app, Web Scripting can sign in for you. You record the steps you take to log in and reach your page, such as entering your username and password and clicking through to a dashboard. OptiSigns then replays those steps on your screens. It also supports sites that use two-factor authentication (2FA).

Your recorded steps and password are encrypted, and are only decrypted on your device. For extra protection, you can add your own **Master Password**.

From **Files/Assets**, select **Apps**, then search for **Web Scripting** and select the **Web Scripting** app.

![Add App dialog searched for Web Scripting, with the Web Scripting app card highlighted](https://support.optisigns.com/hc/article_attachments/56488921904275)

The Web Scripting app settings will open. Paste your recorded steps into **Recorded Script**, and fill in the 2FA fields if your site uses them.

![Web Scripting app form showing the Name, Master Password, Recorded Script and 2FA fields](https://support.optisigns.com/hc/article_attachments/56488885506579)

To record your steps and fill in each field, follow our guide: [How to use the Web Scripting App](./1500012522362-how-to-use-the-web-scripting-app.md).

> **NOTE**
>
> Web Scripting isn't supported on Samsung SSSP smart TVs, LG webOS smart TVs or Apple TV devices.

---

## Option 3: Use Secured Dashboard

Secured Dashboard uses the same recorded steps as Web Scripting. Instead of signing in on each device, it signs in on a secure OptiSigns server and sends a picture of your page to your screens. We recommend it when:

- You use one account with MFA on several screens. Each MFA code works only once, so several devices signing in at the same time can fail.
- You have a mix of device types, such as Windows and Android, and want your report to look the same on all of them.
- Your report is slow to load, and you don't want the loading screen to show.

From **Files/Assets**, select **Apps**, then search for **Secured Dashboard** and select the **Secured Dashboard** app.

![Add App dialog searched for Secured Dashboard, with the Secured Dashboard app card highlighted](https://support.optisigns.com/hc/article_attachments/56488885509139)

The Secured Dashboard app settings will open. Enter a **Name** and paste your recorded steps into **Recorded Script**.

![Secured Dashboard app form showing the Name and Recorded Script fields](https://support.optisigns.com/hc/article_attachments/56488885510419)

For the full steps, follow our guide: [How to use Secured Dashboard App](./19589190970771-how-to-use-secured-dashboard-app.md).

---

## Websites With a Browser Sign-In Pop-up

Some websites ask for your username and password in a small browser pop-up, rather than on a login page. For these, you can add your sign-in details to the start of the URL in the [Website app](./360016382473-how-to-use-the-website-app-and-display-urls-on-optisigns.md), in this form:

https://username:password@www.example.com/

**For example: https://guest:guest@jigsaw.w3.org/HTTP/Basic/**

> **NOTE**
>
> Anyone who can view the asset in your OptiSigns account can see the password in the URL. If that's a concern, use Web Scripting instead.

---

## Signing In on the Device

You can also show a login page in the [Website app](./360016382473-how-to-use-the-website-app-and-display-urls-on-optisigns.md), then connect a mouse and keyboard to the device and sign in there. On a Fire TV Stick, you can connect them with a [USB hub adaptor](https://support.optisigns.com/hc/en-us/articles/360055080914).

We recommend this only as a last resort:

- It doesn't work with every website or device.
- Someone has to be at the device to sign in.
- If the device's cache is cleared, or the website signs you out, someone has to sign in again.

If you can, use one of the options above instead.

### That’s all!

OptiSigns is the leader in [digital signage software](https://www.optisigns.com/). If you have any additional questions, concerns or any feedback about OptiSigns, feel free to reach out to our support team at [support@optisigns.com](mailto:support@optisigns.com).
