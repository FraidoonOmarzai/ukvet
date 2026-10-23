# ukvet Red Flags and Risk Levels

This document explains, in simple terms, why ukvet raises company warning flags and how it chooses an overall risk level.

## Why use rules?

Rules make results consistent and testable. The same facts should produce the same flags each time. The AI does not decide which flags exist. A flag is a reason to check something, not proof that anyone has done anything wrong.

## Red-flag rules

| Rule | When it appears | Why it is useful | Severity |
|---|---|---|---|
| Company status | The company is dissolved, in a formal insolvency/restructuring process, or has another non-active status. Members' voluntary liquidation is treated separately as a solvent wind-up. | Shows whether the company is operating normally or closing down. | High for dissolved/formal failed statuses; medium for other non-active statuses and members' voluntary liquidation. |
| Proposal to strike off | Companies House records an active proposal to strike the company off the register. | Warns that the company's removal from the register is being considered. | High |
| Insolvency record | The company has an insolvency case recorded, unless that event is already covered by the members' voluntary liquidation status rule. | Highlights a formal legal or financial event. | High in general; medium for members' voluntary liquidation. |
| Company age | An active company is less than one year old, or between one and two years old. | New companies have a shorter public track record to review. | Medium if under one year; low if under two years. |
| Accounts overdue | Companies House data says the accounts are overdue. | Draws attention to a missed filing deadline. | Medium |
| Confirmation statement overdue | Companies House data says the confirmation statement is overdue. | Alerts the reviewer that company information may not have been updated on time. | Medium |
| Outstanding secured charges | One or more secured charges remain outstanding. | Shows that a lender may have security over company assets. | Low |
| Directors linked to insolvency cases | Current directors are also appointed at other companies in insolvency processes: one linked company gives low, two gives medium, and three or more gives high. If there are no such cases but at least five linked companies are dissolved, a low flag is raised. | Adds context from directors' other company appointments. | Low, medium, or high depending on the pattern |
| Recent officer changes | Two recent officer appointments/resignations give low; three or more give medium. Appointments around company formation are excluded from the appointment count. | Highlights changes in the people formally recorded for the company. | Low or medium |
| Registered office changes | The registered office has changed at least twice in the period counted by the data source. | Makes repeated address changes visible for review. | Medium |
| No current director recorded | The company is active but no current directors appear in the retrieved data. | May identify missing or unexpected governance information. | Medium |
| No PSC recorded | The company is active but no current Person with Significant Control (PSC) appears in the retrieved data. | Tells the reviewer that control information was not found in the expected form. Some companies may be exempt or have filed a statement instead. | Information only |

## How the overall risk level is chosen

The system does not add up points. It applies these rules in order:

1. **High:** At least one high-severity flag exists.
2. **Insufficient data:** If there is no high flag, but three or more distinct checks could not be completed, the system reports insufficient data.
3. **Medium:** If there is no high flag and fewer than three checks are missing, at least one medium flag makes the result medium.
4. **Low:** If there is no high or medium flag and fewer than three checks are missing, the result is low.

A high flag takes priority over missing data. An informational PSC flag does not count as a red flag in the short assessment summary.

## Important limitations

- A flag is a prompt for further checking, not proof of wrongdoing or financial distress.
- New companies, late filings, secured charges, officer changes and address changes can have ordinary explanations.
- A director's link to another company does not prove that the director caused that company's failure.
- The result depends on the accuracy and completeness of the public-record data retrieved.
- The rules and severity levels are design choices and should be tested against real cases. They are not a guarantee that a company is safe or unsafe.
- If several checks fail, the system may return **insufficient data** rather than pretending it has enough information.
