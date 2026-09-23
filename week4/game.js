const canvas = document.querySelector('#gameCanvas');
const context = canvas.getContext('2d');
const scoreElement = document.querySelector('#score');
const finalScoreElement = document.querySelector('#finalScore');
const startScreen = document.querySelector('#startScreen');
const gameOverScreen = document.querySelector('#gameOverScreen');
const startButton = document.querySelector('#startButton');
const retryButton = document.querySelector('#retryButton');

const GAME_WIDTH = 800;
const GAME_HEIGHT = 450;

const PLAYER_RADIUS = 12;
const PLAYER_ACCELERATION = 900;
const PLAYER_MAX_SPEED = 280;
const PLAYER_DAMPING = 5.5;
const PLAYER_SLOW_RADIUS = 80;
const BLACK_HOLE_RADIUS = 36;
const BLACK_HOLE_COLLISION_RADIUS = BLACK_HOLE_RADIUS + PLAYER_RADIUS;
const BLACK_HOLE_GRAVITY = 2200000;
const MAX_BLACK_HOLE_GRAVITY = 1100;
const BASE_METEOR_INTERVAL = 1.25;
const MIN_METEOR_INTERVAL = 0.42;
const BASE_METEOR_SPEED = 95;
const MAX_METEOR_SPEED = 190;
const MAX_METEORS = 25;

let gameState = 'ready';
let animationId = null;
let previousTime = 0;
let survivalTime = 0;
let meteorTimer = 0;
let isPointerDown = false;
let targetPosition = { x: GAME_WIDTH / 2, y: GAME_HEIGHT - 80 };

const player = {
	x: GAME_WIDTH / 2,
	y: GAME_HEIGHT - 80,
	radius: PLAYER_RADIUS,
	velocityX: 0,
	velocityY: 0
};

const blackHole = {
	x: GAME_WIDTH / 2,
	y: GAME_HEIGHT / 2 + 20,
	radius: BLACK_HOLE_RADIUS,
	rotation: 0
};

const meteors = [];
const stars = createStars();

function createStars() {
	const starList = [];

	for (let index = 0; index < 70; index += 1) {
		starList.push({
			x: Math.random() * GAME_WIDTH,
			y: Math.random() * GAME_HEIGHT,
			radius: Math.random() * 1.5 + 0.4,
			brightness: Math.random() * 0.6 + 0.3
		});
	}

	return starList;
}

function updatePointerPosition(event) {
	// 화면상의 Canvas 크기와 내부 좌표계의 비율을 계산해 입력 위치를 변환한다.
	const rectangle = canvas.getBoundingClientRect();
	targetPosition.x = (event.clientX - rectangle.left) * (GAME_WIDTH / rectangle.width);
	targetPosition.y = (event.clientY - rectangle.top) * (GAME_HEIGHT / rectangle.height);
}

function handlePointerDown(event) {
	isPointerDown = true;
	// pointer capture를 사용하면 포인터가 Canvas 밖으로 나가도 입력을 계속 받을 수 있다.
	canvas.setPointerCapture(event.pointerId);
	updatePointerPosition(event);
}

function handlePointerMove(event) {
	if (isPointerDown) {
		updatePointerPosition(event);
	}
}

function finishPointerInput(event) {
	isPointerDown = false;

	// 이미 capture가 해제된 경우에는 releasePointerCapture를 호출하지 않는다.
	if (canvas.hasPointerCapture(event.pointerId)) {
		canvas.releasePointerCapture(event.pointerId);
	}
}

function resetGame() {
	survivalTime = 0;
	meteorTimer = 0;
	previousTime = 0;
	isPointerDown = false;
	meteors.length = 0;
	player.x = GAME_WIDTH / 2;
	player.y = GAME_HEIGHT - 80;
	player.velocityX = 0;
	player.velocityY = 0;
	targetPosition.x = player.x;
	targetPosition.y = player.y;
	blackHole.rotation = 0;
	scoreElement.textContent = '0';
}

function startGame() {
	if (animationId !== null) {
		cancelAnimationFrame(animationId);
		animationId = null;
	}

	resetGame();
	gameState = 'playing';
	startScreen.hidden = true;
	gameOverScreen.hidden = true;
	animationId = requestAnimationFrame(gameLoop);
}

function endGame() {
	gameState = 'over';
	finalScoreElement.textContent = Math.floor(survivalTime * 100);
	gameOverScreen.hidden = false;
}

function updateGame(deltaTime) {
	survivalTime += deltaTime;
	meteorTimer += deltaTime;
	updatePlayer(deltaTime);
	applyBlackHoleGravity(deltaTime);
	limitPlayerSpeed();
	movePlayer(deltaTime);
	keepPlayerInsideGame();
	updateBlackHole(deltaTime);
	updateMeteors(deltaTime);
	checkCollisions();
	scoreElement.textContent = Math.floor(survivalTime * 100);
}

function updateDifficulty() {
	// 60초 동안 생성 간격은 짧아지고 속도는 최대값까지 증가한다.
	const difficultyLevel = Math.min(survivalTime / 60, 1);
	return {
		meteorInterval: BASE_METEOR_INTERVAL - (BASE_METEOR_INTERVAL - MIN_METEOR_INTERVAL) * difficultyLevel,
		meteorSpeed: BASE_METEOR_SPEED + (MAX_METEOR_SPEED - BASE_METEOR_SPEED) * difficultyLevel
	};
}

function updatePlayer(deltaTime) {
	// 감속은 deltaTime을 사용해 FPS가 달라도 비슷한 속도로 멈추게 한다.
	const dampingAmount = Math.exp(-PLAYER_DAMPING * deltaTime);
	player.velocityX *= dampingAmount;
	player.velocityY *= dampingAmount;

	if (!isPointerDown) {
		return;
	}

	const directionX = targetPosition.x - player.x;
	const directionY = targetPosition.y - player.y;
	const distance = Math.hypot(directionX, directionY);

	if (distance === 0) {
		return;
	}

	// 목표 지점에 가까워질수록 조작 가속도를 줄여서 왕복 움직임을 완화한다.
	const controlAmount = Math.min(distance / PLAYER_SLOW_RADIUS, 1);
	const controlAcceleration = PLAYER_ACCELERATION * controlAmount;
	player.velocityX += (directionX / distance) * controlAcceleration * deltaTime;
	player.velocityY += (directionY / distance) * controlAcceleration * deltaTime;
}

function applyBlackHoleGravity(deltaTime) {
	// 블랙홀까지의 방향을 구한다.
	const directionX = blackHole.x - player.x;
	const directionY = blackHole.y - player.y;
	const distance = Math.hypot(directionX, directionY);
	const safeDistance = Math.max(45, distance);

	// 거리의 제곱에 반비례시켜 가까운 곳에서 중력이 급격히 강해지게 한다.
	const gravity = Math.min(
		MAX_BLACK_HOLE_GRAVITY,
		BLACK_HOLE_GRAVITY / (safeDistance * safeDistance)
	);
	player.velocityX += (directionX / safeDistance) * gravity * deltaTime;
	player.velocityY += (directionY / safeDistance) * gravity * deltaTime;
}

function limitPlayerSpeed() {
	const speed = Math.hypot(player.velocityX, player.velocityY);

	if (speed > PLAYER_MAX_SPEED) {
		const speedScale = PLAYER_MAX_SPEED / speed;
		player.velocityX *= speedScale;
		player.velocityY *= speedScale;
	}
}

function movePlayer(deltaTime) {
	player.x += player.velocityX * deltaTime;
	player.y += player.velocityY * deltaTime;
}

function keepPlayerInsideGame() {
	if (player.x < player.radius) {
		player.x = player.radius;
		if (player.velocityX < 0) {
			player.velocityX = 0;
		}
	}

	if (player.x > GAME_WIDTH - player.radius) {
		player.x = GAME_WIDTH - player.radius;
		if (player.velocityX > 0) {
			player.velocityX = 0;
		}
	}

	if (player.y < player.radius) {
		player.y = player.radius;
		if (player.velocityY < 0) {
			player.velocityY = 0;
		}
	}

	if (player.y > GAME_HEIGHT - player.radius) {
		player.y = GAME_HEIGHT - player.radius;
		if (player.velocityY > 0) {
			player.velocityY = 0;
		}
	}
}

function updateBlackHole(deltaTime) {
	blackHole.rotation += deltaTime * 0.8;
}

function createMeteor() {
	const side = Math.floor(Math.random() * 4);
	const radius = Math.random() * 8 + 8;
	const difficulty = updateDifficulty();
	let x;
	let y;

	if (side === 0) {
		x = Math.random() * GAME_WIDTH;
		y = -radius;
	} else if (side === 1) {
		x = GAME_WIDTH + radius;
		y = Math.random() * GAME_HEIGHT;
	} else if (side === 2) {
		x = Math.random() * GAME_WIDTH;
		y = GAME_HEIGHT + radius;
	} else {
		x = -radius;
		y = Math.random() * GAME_HEIGHT;
	}

	// 화면 중앙 근처의 랜덤한 지점을 향하게 해 운석이 자연스럽게 들어오게 한다.
	const targetX = GAME_WIDTH / 2 + (Math.random() - 0.5) * 260;
	const targetY = GAME_HEIGHT / 2 + (Math.random() - 0.5) * 220;
	const directionX = targetX - x;
	const directionY = targetY - y;
	const distance = Math.hypot(directionX, directionY);
	// 랜덤 배율을 적용하더라도 최종 속도는 최대 속도를 넘지 않게 한다.
	const speed = Math.min(
		MAX_METEOR_SPEED,
		difficulty.meteorSpeed * (Math.random() * 0.35 + 0.85)
	);

	meteors.push({
		x,
		y,
		radius,
		speedX: (directionX / distance) * speed,
		speedY: (directionY / distance) * speed,
		craters: [
			{
				angle: Math.random() * Math.PI * 2,
				offset: radius * 0.35,
				radius: radius * 0.2
			},
			{
				angle: Math.random() * Math.PI * 2,
				offset: radius * 0.48,
				radius: radius * 0.14
			}
		]
	});
}

function updateMeteors(deltaTime) {
	const difficulty = updateDifficulty();

	// 운석 수가 많아지면 새 운석을 잠시 만들지 않아 성능을 보호한다.
	if (meteorTimer >= difficulty.meteorInterval && meteors.length < MAX_METEORS) {
		meteorTimer = 0;
		createMeteor();
	}

	for (let index = meteors.length - 1; index >= 0; index -= 1) {
		const meteor = meteors[index];
		meteor.x += meteor.speedX * deltaTime;
		meteor.y += meteor.speedY * deltaTime;

		if (meteor.x < -80 || meteor.x > GAME_WIDTH + 80 || meteor.y < -80 || meteor.y > GAME_HEIGHT + 80) {
			meteors.splice(index, 1);
		}
	}
}

function checkCollisions() {
	const distanceToBlackHole = Math.hypot(blackHole.x - player.x, blackHole.y - player.y);

	if (distanceToBlackHole < BLACK_HOLE_COLLISION_RADIUS) {
		endGame();
		return;
	}

	for (const meteor of meteors) {
		// 두 원의 중심 거리가 두 반지름의 합보다 작으면 서로 부딪힌 것이다.
		const distance = Math.hypot(meteor.x - player.x, meteor.y - player.y);
		if (distance < player.radius + meteor.radius) {
			endGame();
			return;
		}
	}
}

function drawGame() {
	drawBackground();
	drawBlackHole();
	drawMeteors();
	drawPlayer();
}

function drawBackground() {
	context.fillStyle = '#02040d';
	context.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT);

	for (const star of stars) {
		context.globalAlpha = star.brightness;
		context.fillStyle = '#dceaff';
		context.beginPath();
		context.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
		context.fill();
	}

	context.globalAlpha = 1;
}

function drawPlayer() {
	context.save();
	context.translate(player.x, player.y);
	context.fillStyle = '#77e8ff';
	context.strokeStyle = '#eafaff';
	context.lineWidth = 2;
	context.beginPath();
	context.moveTo(0, -16);
	context.lineTo(12, 12);
	context.lineTo(0, 7);
	context.lineTo(-12, 12);
	context.closePath();
	context.fill();
	context.stroke();
	context.fillStyle = '#ffcf70';
	context.beginPath();
	context.moveTo(-5, 10);
	context.lineTo(0, 19);
	context.lineTo(5, 10);
	context.fill();
	context.restore();
}

function drawBlackHole() {
	const distanceToPlayer = Math.hypot(player.x - blackHole.x, player.y - blackHole.y);
	const dangerAmount = Math.max(0, 1 - distanceToPlayer / 240);

	context.save();
	context.translate(blackHole.x, blackHole.y);
	context.rotate(blackHole.rotation);

	// 플레이어가 가까울수록 강착원반을 조금 더 밝게 그린다.
	context.strokeStyle = `rgba(255, 133, 76, ${0.28 + dangerAmount * 0.25})`;
	context.lineWidth = 16;
	context.beginPath();
	context.ellipse(0, 0, blackHole.radius + 25, blackHole.radius * 0.62, 0, 0, Math.PI * 2);
	context.stroke();

	context.strokeStyle = `rgba(255, 189, 104, ${0.7 + dangerAmount * 0.25})`;
	context.lineWidth = 5;
	context.beginPath();
	context.ellipse(0, 0, blackHole.radius + 13, blackHole.radius * 0.46, 0, 0.15, Math.PI * 1.85);
	context.stroke();

	context.strokeStyle = `rgba(255, 220, 154, ${0.45 + dangerAmount * 0.25})`;
	context.lineWidth = 2;
	context.beginPath();
	context.ellipse(0, 0, blackHole.radius + 6, blackHole.radius * 0.3, 0, 0.25, Math.PI * 1.7);
	context.stroke();

	context.strokeStyle = 'rgba(255, 189, 104, 0.55)';
	context.lineWidth = 2;
	context.setLineDash([6, 6]);
	context.beginPath();
	context.arc(0, 0, BLACK_HOLE_COLLISION_RADIUS, 0, Math.PI * 2);
	context.stroke();
	context.setLineDash([]);

	context.fillStyle = '#000';
	context.beginPath();
	context.arc(0, 0, blackHole.radius, 0, Math.PI * 2);
	context.fill();
	context.restore();
}

function drawMeteors() {
	for (const meteor of meteors) {
		context.fillStyle = '#78869b';
		context.strokeStyle = '#c5d0df';
		context.lineWidth = 2;
		context.beginPath();
		context.arc(meteor.x, meteor.y, meteor.radius, 0, Math.PI * 2);
		context.fill();
		context.stroke();

		for (const crater of meteor.craters) {
			const craterX = meteor.x + Math.cos(crater.angle) * crater.offset;
			const craterY = meteor.y + Math.sin(crater.angle) * crater.offset;
			context.fillStyle = 'rgba(44, 53, 69, 0.7)';
			context.beginPath();
			context.arc(craterX, craterY, crater.radius, 0, Math.PI * 2);
			context.fill();
		}
	}
}

function resizeCanvas() {
	// 내부 좌표는 유지하고 CSS 표시 크기만 바꾸므로 PC와 모바일에서 같은 게임 공간을 사용한다.
	canvas.width = GAME_WIDTH;
	canvas.height = GAME_HEIGHT;
	drawGame();
}

// requestAnimationFrame은 브라우저가 그릴 수 있는 시점에 다음 프레임을 요청한다.
// 이전 프레임과 현재 프레임 사이의 시간 차이를 사용해 FPS가 달라도 속도를 일정하게 만든다.
function gameLoop(currentTime) {
	if (gameState !== 'playing') {
		return;
	}

	if (previousTime === 0) {
		previousTime = currentTime;
	}

	let deltaTime = (currentTime - previousTime) / 1000;
	previousTime = currentTime;
	deltaTime = Math.min(deltaTime, 0.05);

	updateGame(deltaTime);
	drawGame();

	if (gameState === 'playing') {
		animationId = requestAnimationFrame(gameLoop);
	}
}

canvas.addEventListener('pointerdown', handlePointerDown);
canvas.addEventListener('pointermove', handlePointerMove);
canvas.addEventListener('pointerup', finishPointerInput);
canvas.addEventListener('pointercancel', finishPointerInput);
startButton.addEventListener('click', startGame);
retryButton.addEventListener('click', startGame);
window.addEventListener('resize', resizeCanvas);

resizeCanvas();
