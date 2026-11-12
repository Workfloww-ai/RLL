import React, { useState, useEffect } from 'react';
import { 
  FileText, 
  Printer, 
  ArrowLeft, 
  Check, 
  Copy, 
  ShieldCheck, 
  Clock, 
  Building2, 
  ChevronRight,
  MapPin,
  Mail,
  Phone
} from 'lucide-react';

interface TermsSectionItem {
  id: string;
  number: string;
  title: string;
  content: React.ReactNode;
}

export default function TermsAndServices() {
  const [activeSectionId, setActiveSectionId] = useState<string>('preamble');
  const [copiedLink, setCopiedLink] = useState(false);

  useEffect(() => {
    document.title = 'Terms and Conditions | LucidX360';
  }, []);

  const sections: TermsSectionItem[] = [
    {
      id: 'preamble',
      number: '0.0',
      title: 'Preamble & Agreement',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            These Terms and Conditions (&quot;Terms&quot;) govern access to and use of the LucidX360 platform, including its website, web application, mobile application, dashboards, reporting tools, APIs, and associated services (collectively, the &quot;Platform&quot;).
          </p>
          <p>
            The Platform is owned, operated, and provided by Workfloww.ai (&quot;Company&quot;, &quot;Platform Provider&quot;, &quot;we&quot;, &quot;us&quot;, or &quot;our&quot;) to subscribing businesses and enterprises (&quot;Client&quot; or &quot;Client Organization&quot;) and their authorised personnel (&quot;User&quot; or &quot;you&quot;) for legitimate internal business operations.
          </p>
          <p>
            By accessing or using the Platform, you acknowledge that you have read, understood, and agreed to be bound by these Terms, together with the applicable Privacy Policy and any Master Services Agreement (&quot;MSA&quot;) or subscription agreement entered into between Workfloww.ai and your Client Organization.
          </p>
          <div className="p-3.5 rounded-xl bg-amber-50/80 border border-amber-200 text-amber-900 text-xs font-medium">
            <strong>Important:</strong> If you do not agree with these Terms, or if you are not duly authorised by a Client Organization or Workfloww.ai, you must immediately discontinue using the Platform.
          </div>
        </div>
      )
    },
    {
      id: 'general-information',
      number: '1.0',
      title: 'General Information',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            LucidX360 is a multi-tenant business intelligence, field force management, and sales analytics platform designed to support Client Organizations&apos; business operations, sales monitoring, performance analysis, and organisational reporting across industries.
          </p>
          <p className="font-semibold text-slate-800">
            Depending on the Client Organization&apos;s subscription plan and configuration, the Platform may provide access to features and services including:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-[#0D3B8E]">
            <li>Sales performance dashboards and interactive analytical reports.</li>
            <li>Daily, monthly, quarterly, and yearly sales summaries.</li>
            <li>Territory, depot, branch, headquarters, and regional performance tracking.</li>
            <li>Employee, distributor, and sales hierarchy management.</li>
            <li>Field sales personnel (such as TSM, ASE, and regional managers) performance and activity tracking.</li>
            <li>Automated business reports, historical comparisons, and structured data exports.</li>
            <li>Mobile-based access to operational and analytical business information.</li>
            <li>Additional operational, workflow, and analytical functionalities introduced from time to time.</li>
          </ul>
          <p className="pt-1">
            Access to specific modules, datasets, and functionalities of the Platform is governed by role-based access controls (&quot;RBAC&quot;) configured according to each User&apos;s assigned role, organisational responsibilities, and Client Organization permissions.
          </p>
        </div>
      )
    },
    {
      id: 'legal-information',
      number: '2.0',
      title: 'Legal Information',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <div className="overflow-hidden rounded-xl border border-slate-200 shadow-2xs my-2">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100/80 text-slate-800 font-bold border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-4 w-1/3">Attribute</th>
                  <th className="py-2.5 px-4">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                <tr>
                  <td className="py-2.5 px-4 font-semibold text-slate-900">Platform Name</td>
                  <td className="py-2.5 px-4 text-slate-700">LucidX360 (Web and Mobile Applications)</td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-semibold text-slate-900">Platform Operator / Legal Entity</td>
                  <td className="py-2.5 px-4 text-slate-700">Workfloww.ai / Equinox Corp</td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-semibold text-slate-900">Service Model</td>
                  <td className="py-2.5 px-4 text-slate-700">Enterprise B2B Software-as-a-Service (SaaS)</td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-semibold text-slate-900">Governing Jurisdiction</td>
                  <td className="py-2.5 px-4 text-slate-700">India</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="pt-1">
            In the event of any direct conflict between these general Terms and a duly executed written agreement (such as an MSA or Enterprise License Agreement) between Workfloww.ai and a specific Client Organization, the terms of the executed written agreement shall prevail with respect to that Client Organization.
          </p>
        </div>
      )
    },
    {
      id: 'accessing-using',
      number: '3.0',
      title: 'Accessing and Using the Platform',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            Access to LucidX360 is restricted to individuals duly authorised by a subscribing Client Organization or by Workfloww.ai.
          </p>
          <p className="font-semibold text-slate-800">
            By using the Platform, Users agree to:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-[#0D3B8E]">
            <li>Access the Platform exclusively for legitimate business purposes authorised by their Client Organization.</li>
            <li>Provide accurate, current, and complete information when required.</li>
            <li>Operate strictly within their assigned role-based permissions and organisational scope.</li>
            <li>Comply with these Terms, applicable laws, and their Client Organization&apos;s internal policies.</li>
            <li>Refrain from using the Platform for any unlawful, unauthorised, or prohibited activities.</li>
            <li>Safeguard their login credentials and authentication mechanisms at all times.</li>
          </ul>
          <p className="pt-1">
            Users must not use the Platform or any data obtained through it for unauthorised personal, political, promotional, or competing commercial purposes.
          </p>
          <p>
            Workfloww.ai reserves the right to modify, restrict, or discontinue access to any part of the Platform where necessary for operational, security, legal, or contractual reasons.
          </p>
        </div>
      )
    },
    {
      id: 'user-accounts',
      number: '4.0',
      title: 'User Accounts and Security',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            Access to LucidX360 requires authentication through an authorised user account provisioned by your Client Organization&apos;s administrator or by Workfloww.ai.
          </p>
          <p>
            Users are solely responsible for maintaining the confidentiality and security of their account credentials, passwords, one-time passwords (OTPs), tokens, and other authentication details. You agree to:
          </p>
          <ol className="space-y-1.5 pl-5 list-decimal marker:font-bold marker:text-[#0D3B8E]">
            <li>Maintain accurate and up-to-date account profile information.</li>
            <li>Never share login credentials, OTPs, or session access with any other person.</li>
            <li>Immediately report any suspected account compromise, credential leak, or unauthorised access to your Client Organization administrator and Workfloww.ai.</li>
            <li>Log out completely after accessing the Platform on shared or public devices.</li>
            <li>Never attempt to access another User&apos;s account, another department&apos;s restricted records, or another Client Organization&apos;s tenant environment.</li>
            <li>Comply with all multi-factor authentication and security protocols enforced on the Platform.</li>
          </ol>
          <p className="pt-1">
            Workfloww.ai or the respective Client Organization administrator may suspend, restrict, or deactivate accounts where unauthorised access, suspicious activity, employment separation, or violations of these Terms occur.
          </p>
        </div>
      )
    },
    {
      id: 'intellectual-property',
      number: '5.0',
      title: 'Intellectual Property Rights',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            All intellectual property rights in and to the LucidX360 Platform—including its source code, software architecture, algorithms, user interface, visual design, analytics engines, documentation, trademarks, logos, and proprietary materials—are owned exclusively by or licensed to Workfloww.ai.
          </p>
          <p>
            Each Client Organization retains all intellectual property rights in its own corporate trademarks, logos, branding, and proprietary business data uploaded to the Platform.
          </p>
          <p>
            Nothing in these Terms grants any Client Organization or User ownership rights or an implied license to the underlying software or intellectual property of Workfloww.ai. Unless expressly authorised in writing by Workfloww.ai, Users and Client Organizations must not:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-[#0D3B8E]">
            <li>Reproduce, copy, sublicense, lease, resell, or distribute any part of the Platform.</li>
            <li>Modify, adapt, translate, reverse-engineer, decompile, or disassemble the Platform&apos;s software or models.</li>
            <li>Create derivative works based on the Platform or its user interface.</li>
            <li>Remove, obscure, or alter any copyright, trademark, or proprietary notices.</li>
            <li>Use the Platform to build a competing product or service, or benchmark the Platform for public disclosure without prior written consent.</li>
            <li>Use Workfloww.ai&apos;s or any third party&apos;s trademarks, branding, or proprietary materials without authorisation.</li>
          </ul>
        </div>
      )
    },
    {
      id: 'restrictions-acceptable-use',
      number: '6.0',
      title: 'Restrictions on Use and Acceptable Usage Policy',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            Users must use LucidX360 responsibly and in compliance with applicable laws, these Terms, and their Client Organization&apos;s policies. The following activities are strictly prohibited:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-red-500">
            <li>Accessing or attempting to access records, dashboards, or tenant environments without proper authorisation.</li>
            <li>Attempting to bypass authentication mechanisms, tenant isolation boundaries, role-based permissions, or security controls.</li>
            <li>Manipulating, falsifying, fabricating, or deliberately misrepresenting business or field-reporting data.</li>
            <li>Uploading viruses, malware, malicious scripts, or harmful files.</li>
            <li>Disrupting, overloading, damaging, or interfering with Platform infrastructure, servers, or networks.</li>
            <li>Conducting unauthorised penetration testing, security scanning, or vulnerability probing without prior written approval from Workfloww.ai.</li>
            <li>Automated scraping, harvesting, or bulk extracting of Platform data outside approved export or API features.</li>
            <li>Disclosing confidential business data to unauthorised third parties.</li>
            <li>Using Platform data for personal gain, competitive intelligence against other entities, or unlawful purposes.</li>
            <li>Impersonating another User, administrator, or representative.</li>
            <li>Using the Platform in violation of applicable local, national, or international laws and regulations.</li>
          </ul>
          <div className="p-3.5 rounded-xl bg-slate-100 border border-slate-200 text-slate-800 text-xs">
            Workfloww.ai reserves the right to audit usage logs, investigate suspected violations, and take appropriate action, including immediate suspension or termination of access and notification to the relevant Client Organization.
          </div>
        </div>
      )
    },
    {
      id: 'client-data-ownership',
      number: '7.0',
      title: 'Business Information and Client Data Ownership',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            All business information, operational records, and organisational data entered, uploaded, integrated, or generated through LucidX360 on behalf of a Client Organization (&quot;Client Data&quot;) remain the sole property and under the ownership and control of that respective Client Organization, subject to applicable contractual and legal rights.
          </p>
          <p className="font-semibold text-slate-800">
            Client Data may include:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-[#0D3B8E]">
            <li>Sales, inventory, dispatch, and transaction records.</li>
            <li>Employee, field force, distributor, and organisational hierarchy records.</li>
            <li>Territory, depot, branch, and regional performance metrics.</li>
            <li>Business reports, custom dashboards, and analytical outputs.</li>
            <li>Historical datasets and comparative performance records.</li>
            <li>Other commercially sensitive information submitted by or for the Client Organization.</li>
          </ul>
          <p className="pt-1">
            Users are granted access to Client Data solely to perform their authorised duties for their Client Organization. Users must not copy, disclose, distribute, sell, or retain Client Data after termination of their authorisation.
          </p>
          <p>
            Workfloww.ai processes Client Data strictly as a data processor / service provider in accordance with the Client Organization&apos;s instructions, applicable agreements, and data protection laws. Workfloww.ai may engage vetted sub-processors (such as cloud hosting and security providers) to host, process, and secure Client Data under binding confidentiality and security obligations.
          </p>
        </div>
      )
    },
    {
      id: 'accuracy-reporting',
      number: '8.0',
      title: 'Accuracy of Information and Reporting',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            The Platform provides analytical insights, visualisations, and business reports derived from source data supplied by or integrated from the Client Organization and configured calculation logic.
          </p>
          <p>
            While Workfloww.ai employs reasonable technical standards to ensure reliable data processing, Workfloww.ai does not warrant that all outputs, calculations, or reports will be completely error-free or uninterrupted, as report accuracy depends on:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-[#0D3B8E]">
            <li>Completeness, formatting, and accuracy of source data uploaded or synced by the Client Organization.</li>
            <li>Timeliness of data submissions and ERP/CRM synchronisations.</li>
            <li>Client-configured business rules and calculation methodologies.</li>
            <li>Availability and integrity of historical records.</li>
            <li>Third-party network and integration dependencies.</li>
          </ul>
          <p className="pt-1">
            Client Organizations and Users should verify critical financial, tax, or compliance figures against primary accounting or ERP records before making material business decisions. To the extent permitted by applicable law, Workfloww.ai shall not be liable for business decisions made solely on the basis of unverified analytical outputs or inaccurate Client source data.
          </p>
        </div>
      )
    },
    {
      id: 'confidentiality-data-protection',
      number: '9.0',
      title: 'Confidentiality and Data Protection',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            Through LucidX360, Users may access confidential, proprietary, and commercially sensitive information belonging to their Client Organization or to Workfloww.ai (&quot;Confidential Information&quot;).
          </p>
          <p>
            Users must protect Confidential Information using reasonable care and must not disclose, copy, transfer, or share it with unauthorised individuals or external entities. Confidential Information includes:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-[#0D3B8E]">
            <li>Sales figures, pricing structures, margins, and commercial terms.</li>
            <li>Employee, distributor, and customer records.</li>
            <li>Financial, operational, and strategic reports.</li>
            <li>Platform features, non-public documentation, and security configurations.</li>
            <li>Login credentials, API keys, and authentication tokens.</li>
          </ul>
          <p className="pt-1">
            Personal data collected and processed through the Platform is handled in accordance with our Privacy Policy, applicable data protection laws (including the Digital Personal Data Protection Act, 2023 in India, where applicable), and any Data Processing Addendum (&quot;DPA&quot;) executed with the Client Organization.
          </p>
        </div>
      )
    },
    {
      id: 'third-party-services',
      number: '10.0',
      title: 'Third-Party Services and External Links',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            The Platform may integrate with or rely upon third-party infrastructure and services, including cloud hosting providers, database engines, authentication providers, push notification gateways, mapping services, and Client-authorised ERP/CRM integrations.
          </p>
          <p>
            The Platform may also contain links to external websites or third-party tools. Such third-party services operate under their own terms of service and privacy policies. Workfloww.ai does not control independent third-party websites and is not responsible for their standalone content, availability, or practices outside our contractual integrations.
          </p>
        </div>
      )
    },
    {
      id: 'availability-maintenance',
      number: '11.0',
      title: 'Platform Availability and Maintenance',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            Workfloww.ai endeavours to maintain high availability, security, and performance of LucidX360 in accordance with applicable service level commitments. However, uninterrupted or error-free access cannot be guaranteed at all times.
          </p>
          <p className="font-semibold text-slate-800">
            The Platform may experience temporary unavailability or degraded performance due to:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-[#0D3B8E]">
            <li>Scheduled maintenance, patches, and system upgrades.</li>
            <li>Unexpected hardware, cloud infrastructure, or network failures.</li>
            <li>Internet connectivity issues on the User&apos;s or Client Organization&apos;s side.</li>
            <li>Emergency security patches or threat mitigation measures.</li>
            <li>Third-party service or telecommunications provider outages.</li>
            <li>Force majeure events beyond Workfloww.ai&apos;s reasonable control.</li>
          </ul>
          <p className="pt-1">
            Where reasonably practicable, Workfloww.ai will notify Client Organizations or Users in advance of planned maintenance windows or material service updates.
          </p>
        </div>
      )
    },
    {
      id: 'limitation-of-liability',
      number: '12.0',
      title: 'Limitation of Liability',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            To the maximum extent permitted under applicable law, Workfloww.ai shall not be liable for any indirect, incidental, special, punitive, or consequential damages, or loss of profits, revenue, data, or goodwill arising out of or related to the use of or inability to access the Platform, including losses resulting from:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-[#0D3B8E]">
            <li>Temporary service interruptions, scheduled downtime, or network unavailability.</li>
            <li>Errors, omissions, or delays in source data provided by a Client Organization or User.</li>
            <li>Unauthorised account access caused by compromised or shared User credentials.</li>
            <li>Third-party service, telecommunications, or external integration failures.</li>
            <li>Commercial or operational decisions made without independent verification of analytical reports.</li>
          </ul>
          <p className="pt-1">
            Subject to any specific liability cap agreed in an executed MSA with a Client Organization, Workfloww.ai&apos;s aggregate liability arising out of these Terms shall not exceed the fees paid to Workfloww.ai for the User&apos;s access during the twelve (12) months preceding the claim. Nothing in these Terms excludes liability that cannot legally be excluded under applicable law.
          </p>
        </div>
      )
    },
    {
      id: 'user-responsibilities-indemnity',
      number: '13.0',
      title: 'User Responsibilities and Indemnification',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            Users are accountable for all actions performed under their authenticated accounts on LucidX360.
          </p>
          <p>
            To the extent permitted by applicable law, Users and Client Organizations agree to indemnify and hold harmless Workfloww.ai, its affiliates, officers, and employees from and against losses, claims, damages, liabilities, and reasonable legal expenses arising out of:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-[#0D3B8E]">
            <li>Breach of these Terms or applicable laws by the User.</li>
            <li>Unauthorised access, data manipulation, or misuse of Client Data.</li>
            <li>Unauthorised disclosure of Confidential Information.</li>
            <li>Infringement of third-party intellectual property or privacy rights resulting from data uploaded by the User or Client Organization.</li>
          </ul>
          <p className="pt-1">
            Nothing in this section limits any rights or remedies available to a Client Organization against its own personnel under applicable employment or internal policies.
          </p>
        </div>
      )
    },
    {
      id: 'suspension-termination',
      number: '14.0',
      title: 'Suspension and Termination of Access',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            Workfloww.ai (or the respective Client Organization administrator) reserves the right to restrict, suspend, or terminate a User&apos;s access to LucidX360 immediately where:
          </p>
          <ul className="space-y-1.5 pl-4 list-disc marker:text-red-500">
            <li>These Terms or the Acceptable Usage Policy have been violated.</li>
            <li>Unauthorised, fraudulent, or suspicious security activity is detected.</li>
            <li>The User is no longer employed by or authorised by the Client Organization.</li>
            <li>The Client Organization&apos;s subscription expires, terminates, or is suspended for non-payment.</li>
            <li>Continued access poses a security, operational, or legal risk.</li>
          </ul>
          <p className="pt-1">
            Upon termination of a User&apos;s access, all rights granted to that User under these Terms cease immediately. Termination of User access does not affect the Client Organization&apos;s ownership of its Client Data, which shall be handled or returned in accordance with the applicable Client agreement.
          </p>
        </div>
      )
    },
    {
      id: 'modifications-to-terms',
      number: '15.0',
      title: 'Modifications to the Platform and These Terms',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            Workfloww.ai continuously improves LucidX360 and may add, update, modify, or deprecate features, interfaces, and functionalities from time to time.
          </p>
          <p>
            Workfloww.ai reserves the right to update or revise these Terms periodically. Updated versions will be published on the Platform with a revised &quot;Last Updated&quot; date. Continued access to or use of the Platform after the effective date of revised Terms constitutes acceptance of the updated Terms.
          </p>
        </div>
      )
    },
    {
      id: 'privacy-policy',
      number: '16.0',
      title: 'Privacy Policy',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            Personal information collected during account provisioning, authentication, or use of LucidX360 is processed in accordance with the LucidX360 Privacy Policy. The Privacy Policy details the categories of personal data collected, purposes of processing, security safeguards, retention periods, and Users&apos; privacy rights.
          </p>
        </div>
      )
    },
    {
      id: 'cookies-technologies',
      number: '17.0',
      title: 'Cookies and Similar Technologies',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            LucidX360 uses essential cookies, local storage, session tokens, and similar technologies to authenticate Users, maintain secure sessions, enforce role permissions, remember user preferences, and monitor Platform stability. Where applicable, non-essential cookies are governed by our Cookie Policy and applicable consent requirements.
          </p>
        </div>
      )
    },
    {
      id: 'industry-compliance',
      number: '18.0',
      title: 'Industry and Regulatory Compliance',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            LucidX360 is an enterprise business intelligence, field operations, and sales analytics software tool designed strictly for internal organisational management and reporting.
          </p>
          <p>
            The Platform does not function as a consumer-facing e-commerce marketplace or point-of-sale portal for regulated goods, nor does it facilitate direct retail transactions with the general public.
          </p>
          <p>
            Each Client Organization and its Users may operate in regulated or specialised industries (including FMCG, beverages, pharmaceuticals, manufacturing, or distribution) and are solely responsible for ensuring that their business operations, uploaded data, and use of the Platform comply with all applicable national, state, and local laws, sector-specific regulations, and licensing conditions.
          </p>
        </div>
      )
    },
    {
      id: 'applicable-law-jurisdiction',
      number: '19.0',
      title: 'Applicable Law and Jurisdiction',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            These Terms and Conditions shall be governed by and construed in accordance with the laws of India, without regard to conflict-of-law principles.
          </p>
          <p>
            Subject to any dispute resolution clause in an executed MSA with a Client Organization, any disputes arising out of or relating to these Terms or the use of the Platform shall be subject to the exclusive jurisdiction of the competent courts in Gurgaon, Haryana, India.
          </p>
        </div>
      )
    },
    {
      id: 'entire-agreement-severability',
      number: '20.0',
      title: 'Entire Agreement and Severability',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            These Terms, together with the applicable Privacy Policy and any executed Client Organization agreement (such as an MSA or Order Form), constitute the entire understanding governing access to and use of LucidX360.
          </p>
          <p>
            If any provision of these Terms is held to be invalid or unenforceable by a court of competent jurisdiction, the remaining provisions shall remain in full force and effect. Failure by Workfloww.ai to enforce any right or provision under these Terms shall not constitute a waiver of such right or provision.
          </p>
        </div>
      )
    },
    {
      id: 'contact-information',
      number: '21.0',
      title: 'Contact Information',
      content: (
        <div className="space-y-3.5 text-xs sm:text-[13px] text-slate-700 leading-relaxed">
          <p>
            For questions, legal notices, or inquiries regarding these Terms and Conditions or the LucidX360 Platform, please contact:
          </p>
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2 font-medium">
            <p className="font-bold text-slate-900 text-sm">Workfloww.ai</p>
            <p className="flex items-start gap-2 text-slate-600">
              <MapPin className="w-4 h-4 shrink-0 text-[#0D3B8E] mt-0.5" />
              <span>Registered / Corporate Office: Equinox Corp, New Sanganer road, Jaipur</span>
            </p>
            <p className="flex items-center gap-2 text-slate-600">
              <Mail className="w-4 h-4 shrink-0 text-[#0D3B8E]" />
              <span>Legal &amp; Compliance Email: <a href="mailto:manish@workfloww.ai" className="text-[#0D3B8E] underline">manish@workfloww.ai</a></span>
            </p>
            <p className="flex items-center gap-2 text-slate-600">
              <Phone className="w-4 h-4 shrink-0 text-[#0D3B8E]" />
              <span>Phone: <a href="tel:+919211540400" className="text-[#0D3B8E] underline">+91 9211540400</a></span>
            </p>
          </div>
          <p className="text-slate-500 text-xs">
            For day-to-day account provisioning, password resets, or role-permission changes, Users should first contact their respective Client Organization&apos;s designated LucidX360 administrator.
          </p>
          <p className="font-semibold text-slate-800 pt-2 border-t border-slate-100">
            By accessing and using LucidX360, you acknowledge that you have read, understood, and agreed to these Terms and Conditions.
          </p>
        </div>
      )
    }
  ];

  // Update active section on scroll
  useEffect(() => {
    const handleScroll = () => {
      const scrollPosition = window.scrollY + 140;
      for (const section of sections) {
        const el = document.getElementById(section.id);
        if (el) {
          const top = el.offsetTop;
          const height = el.offsetHeight;
          if (scrollPosition >= top && scrollPosition < top + height) {
            setActiveSectionId(section.id);
            break;
          }
        }
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [sections]);

  const scrollToSection = (id: string) => {
    setActiveSectionId(id);
    const element = document.getElementById(id);
    if (element) {
      const yOffset = -90;
      const y = element.getBoundingClientRect().top + window.pageYOffset + yOffset;
      window.scrollTo({ top: y, behavior: 'smooth' });
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  };

  const handleBackToPortal = () => {
    if (window.opener) {
      window.close();
    } else {
      window.location.href = '/';
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans antialiased selection:bg-[#0D3B8E] selection:text-white print:bg-white">
      {/* Sticky Top Header */}
      <header className="sticky top-0 z-30 bg-white/90 backdrop-blur-md border-b border-slate-200/80 shadow-2xs print:hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Brand Info */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleBackToPortal}
              className="p-2 -ml-2 text-slate-500 hover:text-slate-900 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
              title="Return to Portal"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="h-6 w-px bg-slate-200" />
            <div className="flex items-center gap-2.5">
              <img 
                src="/images/workfloww_logo.png" 
                alt="LucidX360 Logo" 
                className="h-8 w-auto object-contain select-none" 
              />
              <div className="hidden sm:block">
                <span className="text-sm font-extrabold text-slate-900 tracking-tight">LucidX360</span>
                <span className="text-[11px] text-[#0D3B8E] font-bold block leading-none">Terms and Conditions</span>
              </div>
            </div>
          </div>

          {/* Header Action Buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyLink}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 transition-colors cursor-pointer"
            >
              {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{copiedLink ? 'Link Copied' : 'Share Link'}</span>
            </button>

            <button
              onClick={handlePrint}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold text-white bg-[#0D3B8E] hover:bg-[#0A2F73] shadow-xs hover:shadow transition-all cursor-pointer"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print / PDF</span>
            </button>
          </div>
        </div>
      </header>

      {/* Hero Banner Section */}
      <section className="bg-gradient-to-b from-white via-slate-50 to-slate-50 border-b border-slate-200/70 pt-10 pb-8 px-4 sm:px-6 lg:px-8 print:border-none print:pt-4 print:pb-2">
        <div className="max-w-7xl mx-auto">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold bg-blue-50 text-[#0D3B8E] border border-blue-200/60 mb-3">
              <ShieldCheck className="w-3.5 h-3.5 text-[#0D3B8E]" />
              <span>Enterprise B2B Agreement</span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight leading-tight">
              TERMS AND CONDITIONS
            </h1>
            <p className="mt-2 text-sm text-slate-600 leading-relaxed">
              These Terms and Conditions govern access to and use of the LucidX360 platform, operated by Workfloww.ai.
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-slate-500 font-medium">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                <span>Effective Date: 1st November 2026</span>
              </span>
              <span className="text-slate-300">•</span>
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                <span>Last Updated: 12th November 2026</span>
              </span>
              <span className="text-slate-300">•</span>
              <span className="flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-slate-400" />
                <span>Operator: Workfloww.ai / Equinox Corp</span>
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content Layout */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 lg:py-10">
        <div className="lg:grid lg:grid-cols-12 lg:gap-8 items-start">
          
          {/* Sticky Table of Contents Sidebar (Desktop) */}
          <aside className="hidden lg:block lg:col-span-4 sticky top-24 print:hidden">
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center gap-2 mb-3 pb-2.5 border-b border-slate-100">
                <FileText className="w-4 h-4 text-[#0D3B8E]" />
                <h2 className="text-xs font-extrabold uppercase tracking-wider text-slate-800">
                  Table of Contents
                </h2>
              </div>
              <nav className="space-y-0.5 max-h-[calc(100vh-220px)] overflow-y-auto pr-1">
                {sections.map((section) => {
                  const isActive = activeSectionId === section.id;
                  return (
                    <button
                      key={section.id}
                      onClick={() => scrollToSection(section.id)}
                      className={`w-full flex items-center justify-between text-left px-3 py-1.5 rounded-lg text-xs transition-colors cursor-pointer ${
                        isActive
                          ? 'bg-blue-50/80 text-[#0D3B8E] font-bold border-l-3 border-[#0D3B8E]'
                          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 font-medium'
                      }`}
                    >
                      <span className="truncate pr-2">
                        <span className="text-slate-400 text-[10px] mr-1.5">{section.number}</span>
                        {section.title}
                      </span>
                      <ChevronRight className={`w-3.5 h-3.5 shrink-0 transition-transform ${isActive ? 'text-[#0D3B8E] translate-x-0.5' : 'text-slate-300'}`} />
                    </button>
                  );
                })}
              </nav>

              <div className="mt-5 pt-4 border-t border-slate-100 text-[11px] text-slate-500">
                <span>Legal inquiries: </span>
                <a href="mailto:manish@workfloww.ai" className="font-bold text-[#0D3B8E] hover:underline">
                  manish@workfloww.ai
                </a>
              </div>
            </div>
          </aside>

          {/* Document Content Pane */}
          <div className="lg:col-span-8 space-y-6">
            {sections.map((section) => (
              <article
                key={section.id}
                id={section.id}
                className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 shadow-xs scroll-mt-24 print:border-none print:shadow-none print:p-0 print:mb-6"
              >
                {/* Section Header */}
                <div className="border-b border-slate-100 pb-3 mb-4">
                  <div className="text-[11px] font-bold text-[#0D3B8E] uppercase tracking-wider mb-1">
                    {section.number === '0.0' ? 'Introduction' : `Section ${section.number}`}
                  </div>
                  <h2 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
                    {section.title}
                  </h2>
                </div>

                {/* Section Content */}
                <div>
                  {section.content}
                </div>
              </article>
            ))}

            {/* Document Footer Note */}
            <div className="bg-slate-100/70 border border-slate-200/80 rounded-2xl p-6 text-center text-xs text-slate-500 space-y-2">
              <p className="font-semibold text-slate-700">
                LucidX360 • Enterprise Business Intelligence Platform
              </p>
              <p>
                Operated by Workfloww.ai / Equinox Corp. © 2026 Workfloww.ai. All Rights Reserved.
              </p>
              <div className="pt-2 flex justify-center gap-4 text-xs font-bold text-[#0D3B8E]">
                <button onClick={handleBackToPortal} className="hover:underline cursor-pointer">
                  Return to Portal
                </button>
                <span>•</span>
                <button onClick={handlePrint} className="hover:underline cursor-pointer">
                  Print Document
                </button>
              </div>
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}
