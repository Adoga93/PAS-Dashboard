# Google Sheet Template Structure

To make the dashboard work, please create a Google Sheet (e.g., named "PAS Tutors Data") with the following two tabs (worksheets):

## 1. Tab Name: `Students`
This sheet will hold the student records.

| Column Name | Description | Example Data |
| :--- | :--- | :--- |
| **Student Name** | Full name of the student | Alice Johnson |
| **Payment Status** | Current payment status | Paid |
| **Academic Progress** | Integer from 0 to 100 | 75 |
| **Attendance** | Percentage of classes attended | 90% |
| **Last Class Date** | Date of the last attended class | 2023-10-27 |
| **Email** | Contact email | alice@example.com |
| **Phone** | Contact phone | 555-0123 |
| **Class Times** | Preferred class times | Mon 4pm, Wed 4pm |
| **Subjects** | Subjects needed | Math, Physics |

*Note: The `Payment Status` should ideally be "Paid", "Pending", or "Overdue".*

## 2. Tab Name: `Reviews`
This sheet will store the check-ins submitted by teachers.

| Column Name | Description | Example Data |
| :--- | :--- | :--- |
| **Timestamp** | Date and time of check-in | 2023-10-28 14:30:00 |
| **Teacher Name** | Name of the teacher | Mr. Smith |
| **Student Name** | Name of the student being reviewed | Alice Johnson |
| **Class Review** | Text comment about the class | Great improvement on algebra. |

## 3. Tab Name: `Teachers`
This sheet will store teacher profiles.

| Column Name | Description | Example Data |
| :--- | :--- | :--- |
| **Name** | Full name | John Smith |
| **Email** | Contact email | john@example.com |
| **Phone** | Contact phone | 555-9876 |
| **Expertise** | Subjects capable of teaching | Math, Chemistry |
| **Assigned Students** | List or notes on students | Alice, Bob |

## Setup Instructions
1. Create this Sheet in your Google Drive.
2. Setup Google Cloud Console project and enable Google Drive and Google Sheets APIs.
3. specific service account, download the JSON key file.
4. **Share the Google Sheet** with the `client_email` found in your JSON key file (give Editor access).
5. Rename the JSON key file to `credentials.json` and place it in the root of your project folder.
