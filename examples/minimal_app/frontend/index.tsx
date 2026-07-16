import React, { useState } from "react";
import { createRoot } from "react-dom/client";

function App() {
	const [count, setCount] = useState(0);

	return (
		<>
			<style>
				{`
				body {
					padding: 0;
					margin: 0;
				}
			`}
			</style>
			<main style={styles.container}>
				<h1>Simple React App</h1>
				<p>Count: {count}</p>
				<button onClick={() => setCount(count + 1)}>Click me</button>
			</main>
		</>
	);
}

const styles = {
	container: {
		minHeight: "100vh",
		display: "flex",
		flexDirection: "column" as const,
		justifyContent: "center",
		alignItems: "center",
		fontFamily: "Arial, sans-serif",
	},
};

createRoot(document.getElementById("app")!).render(
	<React.StrictMode>
		<App />
	</React.StrictMode>,
);
