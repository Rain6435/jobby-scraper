// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';

// Deployed to GitHub Pages as a project site: https://rain6435.github.io/jobby-scraper/
export default defineConfig({
	site: 'https://rain6435.github.io',
	base: '/jobby-scraper',
	integrations: [
		// Must come before Starlight so ```mermaid blocks are transformed first.
		mermaid({ theme: 'default', autoTheme: true }),
		starlight({
			title: 'Jobby Scraper',
			description:
				'A job pool generator: scrapes 1,290+ company career sites across 40+ applicant tracking systems into one normalized SQL database.',
			logo: { src: './src/assets/logo.svg' },
			customCss: ['./src/styles/custom.css'],
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/Rain6435/jobby-scraper' },
			],
			editLink: {
				baseUrl: 'https://github.com/Rain6435/jobby-scraper/edit/main/docs/',
			},
			lastUpdated: true,
			sidebar: [
				{
					label: 'Getting started',
					items: [
						'getting-started/introduction',
						'getting-started/installation',
						'getting-started/quick-start',
					],
				},
				{
					label: 'Guides',
					items: [
						'guides/running-scrapes',
						'guides/adding-companies',
						'guides/writing-a-board-scraper',
						'guides/parsing-single-links',
						'guides/consuming-the-pool',
					],
				},
				{
					label: 'Concepts',
					items: [
						'concepts/architecture',
						'concepts/job-identity-and-diffing',
						'concepts/reliability-and-performance',
						'concepts/locations',
						'concepts/ai-enrichment-and-logos',
					],
				},
				{
					label: 'Reference',
					items: [
						'reference/cli',
						'reference/configuration',
						'reference/boards',
						'reference/database-schema',
						'reference/job-model',
						'reference/environment-variables',
					],
				},
				{
					label: 'Contributing',
					items: ['contributing/development'],
				},
			],
		}),
	],
});
